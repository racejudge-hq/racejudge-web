"""
Precedent search router — Phase 4.

POST /v1/precedents/search
  Hybrid retrieval: pgvector ANN (BGE-M3) + Postgres BM25 fused with RRF (k=60).
  Returns top-20 incident cards with similarity scores and structured metadata.

GET /v1/precedents/{incident_id}/similar
  Returns the pre-computed top-20 precedent_links for a known incident.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from packages.db.database import _get_session_factory

log = logging.getLogger(__name__)
router = APIRouter(tags=["precedents"])

_DB_AVAILABLE = bool(os.environ.get("DATABASE_URL"))


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class PrecedentQuery(BaseModel):
    query: str = Field(min_length=3, description="Natural language incident description")
    season: int | None = Field(None, ge=2018, le=2030)
    penalty_type: str | None = Field(None, description="NFA/REP/5s/10s/DT/GRID/DSQ")
    infraction: str | None = Field(None, description="e.g. causing_a_collision")
    driver: str | None = Field(None, description="Driver code e.g. VER")
    article: str | None = Field(None, description="e.g. 38.1")
    limit: int = Field(20, ge=1, le=50)


class DriverInfo(BaseModel):
    code: str
    full_name: str | None = None
    number: int | None = None


class PrecedentResult(BaseModel):
    incident_id: str
    doc_id: str
    title: str
    season: int
    published_at: str | None = None
    pdf_url: str | None = None
    drivers: list[dict] = []
    infraction_category: str | None = None
    penalty_type: str | None = None
    penalty_seconds: int | None = None
    penalty_points: int = 0
    article_cited: list[str] | None = None
    lap: int | None = None
    corner: str | None = None
    contact: bool | None = None
    reasoning_snippet: str = ""
    similarity_score: float


class PrecedentSearchResponse(BaseModel):
    results: list[PrecedentResult]
    total: int
    mode: str = Field(description="hybrid | bm25_only | empty")
    query: str


# ---------------------------------------------------------------------------
# In-memory fallback when DB is unavailable
# ---------------------------------------------------------------------------

def _fallback_search(query: str, season: int | None, limit: int) -> list[dict]:
    """BM25 over the decisions JSONL — no incident-level data, but better than nothing."""
    from apps.api.routers.search import _bm25_search
    results = _bm25_search(query, season, limit)
    return [
        {
            "incident_id": r["doc_id"],
            "doc_id": r["doc_id"],
            "title": r["title"],
            "season": r["season"],
            "published_at": r.get("published_at"),
            "pdf_url": None,
            "drivers": [],
            "infraction_category": r.get("infraction_type"),
            "penalty_type": r.get("outcome"),
            "penalty_seconds": None,
            "penalty_points": 0,
            "article_cited": None,
            "lap": None,
            "corner": None,
            "contact": None,
            "reasoning_snippet": r.get("snippet", ""),
            "similarity_score": r.get("score", 0.0),
        }
        for r in results
    ]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/precedents/search", response_model=PrecedentSearchResponse)
async def search_precedents(body: PrecedentQuery) -> dict[str, Any]:
    """
    Hybrid precedent search combining semantic (BGE-M3 pgvector) and
    BM25 (Postgres tsvector) results fused with Reciprocal Rank Fusion.
    """
    if not _DB_AVAILABLE:
        fallback = _fallback_search(body.query, body.season, body.limit)
        return {
            "results": fallback,
            "total":   len(fallback),
            "mode":    "bm25_only",
            "query":   body.query,
        }

    factory = _get_session_factory()
    if factory is None:
        fallback = _fallback_search(body.query, body.season, body.limit)
        return {
            "results": fallback,
            "total":   len(fallback),
            "mode":    "bm25_only",
            "query":   body.query,
        }

    from apps.api.retrieval.rrf import hybrid_search

    try:
        async with factory() as db:
            cards = await hybrid_search(
                query=body.query,
                db=db,
                top_k=body.limit,
                season=body.season,
                penalty_type=body.penalty_type,
                infraction=body.infraction,
                driver=body.driver,
            )
    except Exception as exc:
        log.error("Hybrid search failed: %s", exc)
        fallback = _fallback_search(body.query, body.season, body.limit)
        return {
            "results": fallback,
            "total":   len(fallback),
            "mode":    "bm25_only",
            "query":   body.query,
        }

    results = [
        {
            "incident_id":        c["incident_id"],
            "doc_id":             c["doc_id"],
            "title":              c["title"],
            "season":             c["season"],
            "published_at":       str(c["published_at"]) if c.get("published_at") else None,
            "pdf_url":            c.get("pdf_url"),
            "drivers":            c.get("drivers") or [],
            "infraction_category": c.get("infraction_category"),
            "penalty_type":       c.get("penalty_type"),
            "penalty_seconds":    c.get("penalty_seconds"),
            "penalty_points":     c.get("penalty_points") or 0,
            "article_cited":      c.get("article_cited") or [],
            "lap":                c.get("lap"),
            "corner":             c.get("corner"),
            "contact":            c.get("contact"),
            "reasoning_snippet":  (c.get("reasoning_text") or "")[:400],
            "similarity_score":   round(c.get("similarity_score", 0.0), 4),
        }
        for c in cards
    ]

    return {
        "results": results,
        "total":   len(results),
        "mode":    "hybrid",
        "query":   body.query,
    }


@router.get("/precedents/{incident_id}/similar", response_model=list[PrecedentResult])
async def get_similar_incidents(
    incident_id: str,
    limit: int = Query(default=20, ge=1, le=50),
) -> list[dict]:
    """
    Return pre-computed similar incidents from precedent_links table.
    Faster than on-the-fly hybrid search for known incidents.
    """
    if not _DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database unavailable")

    factory = _get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    from sqlalchemy import text

    sql = text("""
        SELECT
            pl.similar_incident_id  AS incident_id,
            i.doc_id,
            d.title,
            d.season,
            d.published_at::text    AS published_at,
            d.pdf_url,
            i.drivers,
            i.infraction_category,
            i.penalty_type,
            i.penalty_seconds,
            i.penalty_points,
            i.article_cited,
            i.lap,
            i.corner,
            i.contact,
            LEFT(i.reasoning_text, 400) AS reasoning_snippet,
            pl.similarity_score
        FROM precedent_links pl
        JOIN incidents i  ON pl.similar_incident_id = i.incident_id
        JOIN decisions d  ON i.doc_id = d.doc_id
        WHERE pl.incident_id = :incident_id
        ORDER BY pl.similarity_score DESC
        LIMIT :limit
    """)

    try:
        async with factory() as db:
            result = await db.execute(sql, {"incident_id": incident_id, "limit": limit})
            rows = result.mappings().all()
    except Exception as exc:
        log.error("Similar incidents query failed: %s", exc)
        raise HTTPException(status_code=500, detail="Query failed") from exc

    if not rows:
        return []

    return [
        {
            "incident_id":        r["incident_id"],
            "doc_id":             r["doc_id"],
            "title":              r["title"],
            "season":             r["season"],
            "published_at":       r["published_at"],
            "pdf_url":            r["pdf_url"],
            "drivers":            r["drivers"] or [],
            "infraction_category": r["infraction_category"],
            "penalty_type":       r["penalty_type"],
            "penalty_seconds":    r["penalty_seconds"],
            "penalty_points":     r["penalty_points"] or 0,
            "article_cited":      list(r["article_cited"]) if r["article_cited"] else [],
            "lap":                r["lap"],
            "corner":             r["corner"],
            "contact":            r["contact"],
            "reasoning_snippet":  r["reasoning_snippet"] or "",
            "similarity_score":   round(float(r["similarity_score"]), 4),
        }
        for r in rows
    ]
