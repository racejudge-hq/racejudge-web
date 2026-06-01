"""
Semantic search using pgvector HNSW index.

Embeds the query with BGE-M3 and returns top-k incident IDs ranked
by cosine similarity to the query embedding.

Returns up to 100 candidates for RRF merging.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any

log = logging.getLogger(__name__)

EMBED_MODEL = os.environ.get("EMBED_MODEL", "BAAI/bge-m3")
EMBED_DIM   = 1024


@lru_cache(maxsize=1)
def _get_embedder():
    """Lazy-load BGE-M3. Returns None if not installed."""
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(EMBED_MODEL)
        log.info("BGE-M3 loaded from %s", EMBED_MODEL)
        return model
    except ImportError:
        log.warning("sentence-transformers not installed — semantic search disabled. "
                    "pip install sentence-transformers")
        return None
    except Exception as exc:
        log.error("BGE-M3 load failed: %s", exc)
        return None


def embed_query(text: str) -> list[float] | None:
    """Embed a query string. Returns None if model unavailable."""
    model = _get_embedder()
    if model is None:
        return None
    try:
        vec = model.encode(text, normalize_embeddings=True)
        return vec.tolist()
    except Exception as exc:
        log.error("Embed failed: %s", exc)
        return None


async def semantic_search(
    query: str,
    db,
    *,
    top_k: int = 100,
    season: int | None = None,
    penalty_type: str | None = None,
    infraction: str | None = None,
    driver: str | None = None,
    ef_search: int = 80,
) -> list[dict]:
    """
    Embed the query and run pgvector ANN search.

    Returns list of {incident_id, score, rank} sorted by cosine similarity DESC.
    Empty list if embeddings not available.
    """
    embedding = embed_query(query)
    if embedding is None:
        return []

    from sqlalchemy import text

    # Build WHERE clause for structured filters
    conditions = ["i.embedding IS NOT NULL"]
    params: dict[str, Any] = {
        "embedding": str(embedding),
        "top_k":     top_k,
        "ef_search": ef_search,
    }

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
        conditions.append("i.drivers @> :driver_filter::jsonb")
        params["driver_filter"] = f'[{{"code":"{driver.upper()}"}}]'

    where = " AND ".join(conditions)

    # Set HNSW ef_search for this query
    await db.execute(text(f"SET LOCAL hnsw.ef_search = {ef_search};"))

    sql = text(f"""
        SELECT
            i.incident_id,
            1 - (i.embedding <=> :embedding::vector) AS score
        FROM incidents i
        LEFT JOIN decisions d ON i.doc_id = d.doc_id
        WHERE {where}
        ORDER BY i.embedding <=> :embedding::vector
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
        log.error("pgvector search failed: %s", exc)
        return []
