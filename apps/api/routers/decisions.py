"""
Decisions router — Phase 1 (JSONL-backed, no DB yet).

Serves parsed decisions from data/parsed/decisions.jsonl.
Phase 1 milestone: full 2024–25 PDFs ingested and browsable via API.
Replaced by a Postgres-backed router in Phase 1 week 2.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(tags=["decisions"])

DECISIONS_JSONL = Path(__file__).resolve().parents[3] / "data" / "parsed" / "decisions.jsonl"


class Decision(BaseModel):
    doc_id: str
    title: str
    pdf_url: str
    season: int
    published_at: str | None
    char_count: int
    needs_ocr: bool
    parsed_at: str


class DecisionDetail(Decision):
    raw_text: str
    sha256_hash: str
    r2_key: str


@lru_cache(maxsize=1)
def _load_decisions() -> list[dict]:
    if not DECISIONS_JSONL.exists():
        return []
    return [json.loads(line) for line in DECISIONS_JSONL.read_text().splitlines() if line.strip()]


@router.get("/decisions", response_model=list[Decision])
async def list_decisions(
    season: Annotated[int | None, Query(description="Filter by F1 calendar year")] = None,
    q: Annotated[str | None, Query(description="Case-insensitive title search")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict]:
    records = _load_decisions()
    if season is not None:
        records = [r for r in records if r.get("season") == season]
    if q:
        q_lower = q.lower()
        records = [r for r in records if q_lower in r.get("title", "").lower()]
    return records[offset : offset + limit]


@router.get("/decisions/{doc_id}", response_model=DecisionDetail)
async def get_decision(doc_id: str) -> dict:
    for r in _load_decisions():
        if r.get("doc_id") == doc_id:
            return r
    raise HTTPException(status_code=404, detail=f"Decision {doc_id!r} not found")
