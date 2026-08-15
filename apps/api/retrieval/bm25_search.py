"""
BM25 full-text search using PostgreSQL tsvector + ts_rank_cd.

Searches across incidents.reasoning_text (weight A) and
decisions.raw_text (weight B) for structured incident-level retrieval.

Returns up to 100 candidates with ts_rank scores for RRF merging.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


async def bm25_search(
    query: str,
    db,
    *,
    top_k: int = 100,
    season: int | None = None,
    penalty_type: str | None = None,
    infraction: str | None = None,
    driver: str | None = None,
) -> list[dict]:
    """
    PostgreSQL full-text search over incidents + decisions.

    Returns list of {incident_id, score, rank} sorted by ts_rank_cd DESC.
    """
    from sqlalchemy import text

    # query.q, not query: bare `query` names the CTE, so Postgres reads it as a
    # whole-row record and rejects `tsvector @@ record`. Every call raised
    # UndefinedFunctionError and was swallowed by the except below, so BM25
    # silently returned nothing and hybrid search ran on vectors alone.
    conditions = ["(to_tsvector('english', i.reasoning_text) @@ query.q OR "
                  " d.search_vector @@ query.q)"]
    params: dict[str, Any] = {"q": query, "top_k": top_k}

    if season:
        conditions.append("d.season = :season")
        params["season"] = season
    if penalty_type:
        conditions.append("i.penalty_type = :penalty_type")
        params["penalty_type"] = penalty_type.upper()
    if infraction:
        conditions.append("i.infraction_category = :infraction")
        params["infraction"] = infraction
    if driver:
        conditions.append("i.drivers @> CAST(:driver_filter AS jsonb)")
        params["driver_filter"] = f'[{{"code":"{driver.upper()}"}}]'

    where = " AND ".join(conditions)

    sql = text(f"""
        WITH query AS (
            SELECT plainto_tsquery('english', :q) AS q
        )
        SELECT
            i.incident_id,
            ts_rank_cd(
                setweight(to_tsvector('english', coalesce(i.reasoning_text, '')), 'A') ||
                setweight(coalesce(d.search_vector, to_tsvector('')), 'B'),
                query.q
            ) AS score
        FROM incidents i
        LEFT JOIN decisions d ON i.doc_id = d.doc_id
        CROSS JOIN query
        WHERE {where}
        ORDER BY score DESC
        LIMIT :top_k
    """)

    try:
        result = await db.execute(sql, params)
        rows = result.all()
        return [
            {"incident_id": row[0], "score": float(row[1]), "rank": i + 1}
            for i, row in enumerate(rows)
        ]
    except Exception as exc:
        log.error("BM25 search failed: %s", exc)
        return []
