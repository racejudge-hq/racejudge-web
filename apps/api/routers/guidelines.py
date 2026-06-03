"""
Guidelines router — Phase 6.

GET /v1/guidelines               — list all FIA guideline articles
GET /v1/guidelines/{article_id}  — single article with linked decisions
"""

from __future__ import annotations

import logging
import os
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

log    = logging.getLogger(__name__)
router = APIRouter(tags=["guidelines"])

_DB_AVAILABLE = bool(os.environ.get("DATABASE_URL"))


class GuidelineRow(BaseModel):
    article_id:          str
    document_name:       str
    section:             str | None = None
    article_number:      str
    article_text:        str
    recommended_penalty: str | None = None
    effective_date:      str | None = None


class GuidelineDetail(GuidelineRow):
    linked_decisions: list[dict] = []


# ---------------------------------------------------------------------------
# In-memory fallback when DB absent (10-row seed from guidelines_parser.py)
# ---------------------------------------------------------------------------

_SEED: list[dict[str, Any]] = [
    {
        "article_id":          "seed-001",
        "document_name":       "2025 FIA Sporting Regulations",
        "section":             "Chapter 4 — Race Incidents",
        "article_number":      "38.1",
        "article_text":        (
            "A driver must make every reasonable effort to avoid a collision "
            "with another competitor and must avoid causing avoidable accidents."
        ),
        "recommended_penalty": "5s–10s",
        "effective_date":      "2025-01-01",
    },
    {
        "article_id":          "seed-002",
        "document_name":       "2025 FIA Sporting Regulations",
        "section":             "Chapter 4 — Race Incidents",
        "article_number":      "54.3",
        "article_text":        (
            "No driver may leave the track without a justifiable reason. "
            "Gaining a lasting advantage by leaving the track will result in a "
            "time penalty or instruction to give the position back."
        ),
        "recommended_penalty": "REP–5s",
        "effective_date":      "2025-01-01",
    },
    {
        "article_id":          "seed-003",
        "document_name":       "2025 FIA Sporting Regulations",
        "section":             "Chapter 5 — Pit Lane",
        "article_number":      "34.7",
        "article_text":        (
            "No car may be released from a garage or pit stop position into "
            "the path of an approaching car in a manner that could be "
            "deemed potentially dangerous."
        ),
        "recommended_penalty": "5s–10s",
        "effective_date":      "2025-01-01",
    },
]


# ---------------------------------------------------------------------------
# DB query helpers
# ---------------------------------------------------------------------------

async def _pg_list(
    document_name: str | None,
    limit: int,
    offset: int,
) -> list[dict]:
    from sqlalchemy import select

    from packages.db.database import _get_session_factory
    from packages.db.models import Guideline

    factory = _get_session_factory()
    if factory is None:
        return _SEED

    stmt = select(Guideline).order_by(
        Guideline.document_name,
        Guideline.article_number,
    )
    if document_name:
        stmt = stmt.where(Guideline.document_name.ilike(f"%{document_name}%"))
    stmt = stmt.offset(offset).limit(limit)

    async with factory() as db:
        result = await db.execute(stmt)
        rows   = result.scalars().all()

    if not rows:
        return _SEED  # always show seed if table empty

    return [
        {
            "article_id":          r.article_id,
            "document_name":       r.document_name,
            "section":             r.section,
            "article_number":      r.article_number,
            "article_text":        r.article_text,
            "recommended_penalty": r.recommended_penalty,
            "effective_date":      str(r.effective_date) if r.effective_date else None,
        }
        for r in rows
    ]


async def _pg_get(article_id: str) -> dict | None:
    from sqlalchemy import select, text

    from packages.db.database import _get_session_factory
    from packages.db.models import Guideline

    factory = _get_session_factory()
    if factory is None:
        return next((r for r in _SEED if r["article_id"] == article_id), None)

    async with factory() as db:
        result = await db.execute(
            select(Guideline).where(Guideline.article_id == article_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None

        # Fetch decisions that cite this article number
        linked = await db.execute(text("""
            SELECT d.doc_id, d.title, d.season, d.published_at::text,
                   i.penalty_type, i.infraction_category
            FROM incidents i
            JOIN decisions d ON i.doc_id = d.doc_id
            WHERE :article_number = ANY(i.article_cited)
            ORDER BY d.season DESC, d.published_at DESC
            LIMIT 20
        """), {"article_number": row.article_number})
        linked_rows = linked.mappings().all()

    return {
        "article_id":          row.article_id,
        "document_name":       row.document_name,
        "section":             row.section,
        "article_number":      row.article_number,
        "article_text":        row.article_text,
        "recommended_penalty": row.recommended_penalty,
        "effective_date":      str(row.effective_date) if row.effective_date else None,
        "linked_decisions":    [dict(r) for r in linked_rows],
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/guidelines", response_model=list[GuidelineRow])
async def list_guidelines(
    document_name: Annotated[str | None, Query(description="Filter by document name (partial match)")] = None,
    limit:         Annotated[int,         Query(ge=1, le=500)] = 200,
    offset:        Annotated[int,         Query(ge=0)] = 0,
) -> list[dict]:
    if not _DB_AVAILABLE:
        return _SEED
    try:
        return await _pg_list(document_name, limit, offset)
    except Exception as exc:
        log.error("Guidelines list failed: %s", exc)
        return _SEED


@router.get("/guidelines/{article_id}", response_model=GuidelineDetail)
async def get_guideline(article_id: str) -> dict:
    if not _DB_AVAILABLE:
        row = next((r for r in _SEED if r["article_id"] == article_id), None)
        if row is None:
            raise HTTPException(status_code=404, detail="Article not found")
        return {**row, "linked_decisions": []}

    result = await _pg_get(article_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Article {article_id!r} not found")
    return result
