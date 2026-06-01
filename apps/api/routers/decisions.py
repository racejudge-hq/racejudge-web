"""
Decisions router — dual-backend: Postgres (preferred) with JSONL fallback.

When DATABASE_URL is set: queries Postgres decisions table with full FTS.
When DATABASE_URL is absent: falls back to JSONL for local dev without a DB.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(tags=["decisions"])

DECISIONS_JSONL = Path(__file__).resolve().parents[3] / "data" / "parsed" / "decisions.jsonl"
_DB_AVAILABLE = bool(os.environ.get("DATABASE_URL"))


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class Decision(BaseModel):
    doc_id: str
    title: str
    pdf_url: str
    season: int
    published_at: str | None = None
    char_count: int = 0
    needs_ocr: bool = False
    parsed_at: str = ""
    infraction_type: str | None = None
    outcome: str | None = None
    car_number: int | None = None
    driver_name: str | None = None

    model_config = {"from_attributes": True}


class DecisionDetail(Decision):
    raw_text: str = ""
    sha256_hash: str = ""
    r2_key: str | None = None
    lap_number: int | None = None
    session_type: str | None = None
    penalty_points: int | None = None
    article_cited: list[str] | None = None


# ---------------------------------------------------------------------------
# JSONL fallback (Phase 1 / no DB)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _load_decisions_jsonl() -> list[dict]:
    if not DECISIONS_JSONL.exists():
        return []
    records = []
    for line in DECISIONS_JSONL.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


# ---------------------------------------------------------------------------
# Postgres helpers
# ---------------------------------------------------------------------------

async def _pg_list(
    season: int | None,
    q: str | None,
    limit: int,
    offset: int,
) -> list[dict]:
    from sqlalchemy import select, text
    from packages.db.database import _get_session_factory
    from packages.db.models import Decision as DecisionModel

    factory = _get_session_factory()
    if factory is None:
        return []

    async with factory() as db:
        stmt = select(DecisionModel).order_by(DecisionModel.season.desc(), DecisionModel.parsed_at.desc())
        if season is not None:
            stmt = stmt.where(DecisionModel.season == season)
        if q:
            stmt = stmt.where(
                text("search_vector @@ plainto_tsquery('english', :q)").bindparams(q=q)
            )
        stmt = stmt.offset(offset).limit(limit)
        result = await db.execute(stmt)
        rows = result.scalars().all()
        return [_model_to_dict(r) for r in rows]


async def _pg_get(doc_id: str) -> dict | None:
    from sqlalchemy import select
    from packages.db.database import _get_session_factory
    from packages.db.models import Decision as DecisionModel

    factory = _get_session_factory()
    if factory is None:
        return None

    async with factory() as db:
        result = await db.execute(
            select(DecisionModel).where(DecisionModel.doc_id == doc_id)
        )
        row = result.scalar_one_or_none()
        return _model_to_dict(row, detail=True) if row else None


def _model_to_dict(row, detail: bool = False) -> dict:
    d = {
        "doc_id":         row.doc_id,
        "title":          row.title,
        "pdf_url":        row.pdf_url,
        "season":         row.season,
        "published_at":   row.published_at,
        "char_count":     row.char_count,
        "needs_ocr":      row.needs_ocr,
        "parsed_at":      str(row.parsed_at) if row.parsed_at else "",
    }
    if detail:
        d.update({
            "raw_text":    row.raw_text,
            "sha256_hash": row.sha256_hash,
            "r2_key":      row.r2_key,
        })
    return d


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/decisions", response_model=list[Decision])
async def list_decisions(
    season: Annotated[int | None, Query(description="Filter by F1 calendar year")] = None,
    q: Annotated[str | None, Query(description="Full-text search")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict]:
    if _DB_AVAILABLE:
        try:
            return await _pg_list(season, q, limit, offset)
        except Exception:
            pass  # fall through to JSONL

    # JSONL fallback
    records = _load_decisions_jsonl()
    if season is not None:
        records = [r for r in records if r.get("season") == season]
    if q:
        q_lower = q.lower()
        records = [
            r for r in records
            if q_lower in r.get("title", "").lower()
            or q_lower in r.get("raw_text", "").lower()
        ]
    return records[offset: offset + limit]


@router.get("/decisions/{doc_id}", response_model=DecisionDetail)
async def get_decision(doc_id: str) -> dict:
    if _DB_AVAILABLE:
        try:
            row = await _pg_get(doc_id)
            if row:
                return row
        except Exception:
            pass

    # JSONL fallback
    for r in _load_decisions_jsonl():
        if r.get("doc_id") == doc_id:
            return r
    raise HTTPException(status_code=404, detail=f"Decision {doc_id!r} not found")
