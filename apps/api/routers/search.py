"""
Search router — dual backend.

Postgres: tsvector @@ plainto_tsquery with ranked results (ts_rank_cd).
Fallback: in-memory BM25 over JSONL when DATABASE_URL is absent.
"""

from __future__ import annotations

import math
import os
import re
from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter(tags=["search"])
_DB_AVAILABLE = bool(os.environ.get("DATABASE_URL"))


class SearchResult(BaseModel):
    doc_id: str
    title: str
    season: int
    published_at: str | None = None
    infraction_type: str | None = None
    outcome: str | None = None
    score: float
    snippet: str


# ---------------------------------------------------------------------------
# Postgres FTS
# ---------------------------------------------------------------------------

async def _pg_search(q: str, season: int | None, limit: int) -> list[dict]:
    from sqlalchemy import text

    from packages.db.database import _get_session_factory

    factory = _get_session_factory()
    if factory is None:
        return []

    season_clause = "AND season = :season" if season else ""
    sql = text(f"""
        SELECT
            doc_id, title, season, published_at,
            ts_rank_cd(search_vector, query) AS score,
            ts_headline('english', raw_text, query,
                'MaxWords=30, MinWords=15, ShortWord=3,
                 HighlightAll=false, MaxFragments=1') AS snippet
        FROM decisions, plainto_tsquery('english', :q) query
        WHERE search_vector @@ query
          {season_clause}
        ORDER BY score DESC
        LIMIT :limit
    """)

    params: dict = {"q": q, "limit": limit}
    if season:
        params["season"] = season

    async with factory() as db:
        result = await db.execute(sql, params)
        rows = result.mappings().all()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# BM25 in-memory fallback
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _snippet(text: str, query_tokens: list[str], window: int = 200) -> str:
    lower = text.lower()
    for tok in query_tokens:
        idx = lower.find(tok)
        if idx != -1:
            start = max(0, idx - 60)
            end = min(len(text), idx + window)
            raw = text[start:end].strip()
            return ("…" if start > 0 else "") + raw + ("…" if end < len(text) else "")
    return text[:window].strip() + "…"


def _bm25(
    query_tokens: list[str],
    doc_tokens: list[str],
    doc_freq: dict[str, int],
    num_docs: int,
    avg_dl: float,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    tf_map = Counter(doc_tokens)
    dl = len(doc_tokens)
    score = 0.0
    for tok in set(query_tokens):
        tf = tf_map.get(tok, 0)
        df = doc_freq.get(tok, 0)
        if df == 0:
            continue
        idf = math.log((num_docs - df + 0.5) / (df + 0.5) + 1)
        tf_norm = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avg_dl))
        score += idf * tf_norm
    return score


def _bm25_search(q: str, season: int | None, limit: int) -> list[dict]:
    from apps.api.routers.decisions import _load_decisions_jsonl

    records = _load_decisions_jsonl()
    if season:
        records = [r for r in records if r.get("season") == season]
    if not records:
        return []

    query_tokens = _tokenize(q)
    if not query_tokens:
        return []

    tokenized = [
        _tokenize(r.get("title", "") + " " + r.get("raw_text", ""))
        for r in records
    ]

    doc_freq: dict[str, int] = Counter()
    for toks in tokenized:
        for tok in set(toks):
            doc_freq[tok] += 1

    avg_dl = sum(len(t) for t in tokenized) / max(len(tokenized), 1)
    num_docs = len(records)

    scored = []
    for rec, doc_tokens in zip(records, tokenized, strict=False):
        score = _bm25(query_tokens, doc_tokens, doc_freq, num_docs, avg_dl)
        if score > 0:
            scored.append((score, rec))

    scored.sort(key=lambda x: x[0], reverse=True)

    return [
        {
            "doc_id":         r["doc_id"],
            "title":          r["title"],
            "season":         r["season"],
            "published_at":   r.get("published_at"),
            "infraction_type": r.get("infraction_type"),
            "outcome":        r.get("outcome"),
            "score":          round(s, 4),
            "snippet":        _snippet(r.get("raw_text", r.get("title", "")), query_tokens),
        }
        for s, r in scored[:limit]
    ]


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.get("/search", response_model=list[SearchResult])
async def search_decisions(
    q: Annotated[str, Query(description="Search query", min_length=2)],
    season: Annotated[int | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[dict]:
    if _DB_AVAILABLE:
        try:
            results = await _pg_search(q, season, limit)
            if results:
                return results
        except Exception:
            pass

    return _bm25_search(q, season, limit)
