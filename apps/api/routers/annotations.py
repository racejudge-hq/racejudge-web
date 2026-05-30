"""
Annotation / labelling API — Phase 2 (human-in-the-loop).

Provides endpoints to:
  - Queue incidents for human review
  - Submit structured labels (outcome, infraction, relevance triplets)
  - Export annotation_pairs for BGE-M3 fine-tuning

Labels stored in annotation_pairs table (or JSONL fallback for Phase 1).
Target: 500 hand-labelled pairs from Pre-Work Action 2.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(tags=["annotations"])

ANNOTATIONS_PATH = Path(__file__).resolve().parents[3] / "data" / "annotations.jsonl"
ANNOTATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class AnnotationLabel(BaseModel):
    """Human label for a single decision document."""
    doc_id: str
    annotator: str = Field(default="anonymous", description="Annotator identifier")

    # Structured corrections / confirmations
    infraction_type: str | None = None
    outcome: str | None = None
    penalty_class: str | None = None   # NFA | REP | 5s | 10s | DT | GRID | DSQ
    penalty_points: int | None = None
    article_cited: str | None = None
    notes: str | None = None

    # Triplet relevance for embedding fine-tuning
    # anchor_doc_id + positive_doc_id = semantically similar pair
    # anchor_doc_id + negative_doc_id = dissimilar pair
    positive_doc_id: str | None = None
    negative_doc_id: str | None = None


class AnnotationRecord(BaseModel):
    annotation_id: str
    doc_id: str
    annotator: str
    created_at: str
    label: dict


class ExportRow(BaseModel):
    anchor_doc_id: str
    positive_doc_id: str
    negative_doc_id: str | None = None
    annotator: str
    created_at: str


# ---------------------------------------------------------------------------
# Storage helpers (JSONL-backed; replaced by Postgres in Phase 2 week 2)
# ---------------------------------------------------------------------------

def _load_annotations() -> list[dict]:
    if not ANNOTATIONS_PATH.exists():
        return []
    records = []
    with open(ANNOTATIONS_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def _append_annotation(record: dict) -> None:
    with open(ANNOTATIONS_PATH, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/annotations", response_model=list[AnnotationRecord])
async def list_annotations(
    doc_id: Annotated[str | None, Query()] = None,
    annotator: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[dict]:
    """List annotation records, optionally filtered by doc_id or annotator."""
    records = _load_annotations()
    if doc_id:
        records = [r for r in records if r.get("doc_id") == doc_id]
    if annotator:
        records = [r for r in records if r.get("annotator") == annotator]
    return records[:limit]


@router.post("/annotations", response_model=AnnotationRecord, status_code=201)
async def submit_annotation(
    label: Annotated[AnnotationLabel, Body()],
) -> dict:
    """
    Submit a human annotation label for a decision document.
    If positive_doc_id is provided, also creates a relevance triplet.
    """
    annotation_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    record = {
        "annotation_id": annotation_id,
        "doc_id": label.doc_id,
        "annotator": label.annotator,
        "created_at": created_at,
        "label": {
            "infraction_type": label.infraction_type,
            "outcome": label.outcome,
            "penalty_class": label.penalty_class,
            "penalty_points": label.penalty_points,
            "article_cited": label.article_cited,
            "notes": label.notes,
            "positive_doc_id": label.positive_doc_id,
            "negative_doc_id": label.negative_doc_id,
        },
    }
    _append_annotation(record)
    return record


@router.get("/annotations/{annotation_id}", response_model=AnnotationRecord)
async def get_annotation(annotation_id: str) -> dict:
    """Fetch a single annotation by ID."""
    records = _load_annotations()
    for r in records:
        if r.get("annotation_id") == annotation_id:
            return r
    raise HTTPException(status_code=404, detail=f"Annotation {annotation_id} not found")


@router.delete("/annotations/{annotation_id}", status_code=204)
async def delete_annotation(annotation_id: str) -> None:
    """
    Remove an annotation (rewrites JSONL without the record).
    Phase 2 replaces with Postgres soft-delete.
    """
    records = _load_annotations()
    filtered = [r for r in records if r.get("annotation_id") != annotation_id]
    if len(filtered) == len(records):
        raise HTTPException(status_code=404, detail=f"Annotation {annotation_id} not found")
    # Rewrite file
    with open(ANNOTATIONS_PATH, "w") as f:
        for r in filtered:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


@router.get("/annotations/export/triplets", response_model=list[ExportRow])
async def export_triplets() -> list[dict]:
    """
    Export all (anchor, positive, negative?) triplets for BGE-M3 fine-tuning.
    Only returns annotations that have positive_doc_id set.
    """
    records = _load_annotations()
    triplets = []
    for r in records:
        label = r.get("label", {})
        if label.get("positive_doc_id"):
            triplets.append({
                "anchor_doc_id": r["doc_id"],
                "positive_doc_id": label["positive_doc_id"],
                "negative_doc_id": label.get("negative_doc_id"),
                "annotator": r.get("annotator", "anonymous"),
                "created_at": r.get("created_at", ""),
            })
    return triplets


@router.get("/annotations/stats/summary")
async def annotation_stats() -> dict:
    """Return annotation progress toward the 500-pair target."""
    records = _load_annotations()
    total = len(records)
    with_triplets = sum(
        1 for r in records if r.get("label", {}).get("positive_doc_id")
    )
    by_annotator: dict[str, int] = {}
    for r in records:
        annotator = r.get("annotator", "anonymous")
        by_annotator[annotator] = by_annotator.get(annotator, 0) + 1

    return {
        "total_annotations": total,
        "triplet_pairs": with_triplets,
        "target_pairs": 500,
        "progress_pct": round(with_triplets / 500 * 100, 1),
        "by_annotator": by_annotator,
    }
