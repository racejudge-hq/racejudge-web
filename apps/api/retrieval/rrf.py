"""
Reciprocal Rank Fusion (RRF) — merges semantic + BM25 result lists.

Formula: score(d) = Σ 1 / (k + rank_i)  where k = 60 (standard)

Then fetches full incident details for the top-k fused results.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

log = logging.getLogger(__name__)

RRF_K = 60  # standard constant — reduces sensitivity to rank 1 outliers


def reciprocal_rank_fusion(
    result_lists: list[list[dict]],
    *,
    k: int = RRF_K,
    top_k: int = 20,
) -> list[dict]:
    """
    Merge multiple ranked lists using RRF.

    Args:
        result_lists: Each list is [{incident_id, score, rank}, ...] already sorted by rank.
        k:            RRF constant (default 60).
        top_k:        Number of results to return.

    Returns:
        List of {incident_id, rrf_score} sorted by rrf_score DESC, length <= top_k.
    """
    scores: dict[str, float] = defaultdict(float)

    for result_list in result_lists:
        for item in result_list:
            iid  = item["incident_id"]
            rank = item.get("rank", 1)
            scores[iid] += 1.0 / (k + rank)

    merged = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [
        {"incident_id": iid, "rrf_score": round(score, 6)}
        for iid, score in merged[:top_k]
    ]


async def fetch_incident_cards(
    incident_ids: list[str],
    db,
) -> list[dict]:
    """
    Fetch full incident + decision details for a list of incident_ids.
    Preserves the order of incident_ids.
    """
    if not incident_ids:
        return []

    from sqlalchemy import select

    from packages.db.models import Decision, Incident

    # Fetch all at once, then reorder
    result = await db.execute(
        select(
            Incident.incident_id,
            Incident.doc_id,
            Incident.drivers,
            Incident.involved_drivers,
            Incident.lap,
            Incident.corner,
            Incident.article_cited,
            Incident.infraction_category,
            Incident.penalty_type,
            Incident.penalty_seconds,
            Incident.penalty_points,
            Incident.contact,
            Incident.reasoning_text,
            Decision.title,
            Decision.season,
            Decision.published_at,
            Decision.pdf_url,
        )
        .join(Decision, Incident.doc_id == Decision.doc_id)
        .where(Incident.incident_id.in_(incident_ids))
    )
    rows = result.all()

    by_id: dict[str, dict] = {}
    for row in rows:
        by_id[row.incident_id] = {
            "incident_id":        row.incident_id,
            "doc_id":             row.doc_id,
            "drivers":            row.drivers or [],
            "involved_drivers":   row.involved_drivers or [],
            "lap":                row.lap,
            "corner":             row.corner,
            "article_cited":      row.article_cited or [],
            "infraction_category": row.infraction_category,
            "penalty_type":       row.penalty_type,
            "penalty_seconds":    row.penalty_seconds,
            "penalty_points":     row.penalty_points or 0,
            "contact":            row.contact,
            "reasoning_text":     (row.reasoning_text or "")[:500],
            "title":              row.title,
            "season":             row.season,
            "published_at":       row.published_at,
            "pdf_url":            row.pdf_url,
        }

    # Return in the requested order (RRF rank order)
    return [by_id[iid] for iid in incident_ids if iid in by_id]


async def hybrid_search(
    query: str,
    db,
    *,
    top_k: int = 20,
    season: int | None = None,
    penalty_type: str | None = None,
    infraction: str | None = None,
    driver: str | None = None,
    article: str | None = None,
) -> list[dict]:
    """
    Full hybrid retrieval pipeline:
      1. Run semantic search (pgvector)
      2. Run BM25 search (tsvector)
      3. Fuse with RRF
      4. Fetch full incident cards
      5. Return top_k results with rrf_score

    Falls back to BM25-only if embeddings not available.
    """
    from apps.api.retrieval.bm25_search import bm25_search
    from apps.api.retrieval.semantic_search import semantic_search

    filter_kwargs: dict[str, Any] = {
        "season": season,
        "penalty_type": penalty_type,
        "infraction": infraction,
        "driver": driver,
    }

    # Run both in parallel via gather-like sequential (asyncio would need separate tasks)
    sem_results = await semantic_search(query, db, top_k=100, **filter_kwargs)
    bm25_results = await bm25_search(query, db, top_k=100, **filter_kwargs)

    result_lists = []
    if sem_results:
        result_lists.append(sem_results)
    if bm25_results:
        result_lists.append(bm25_results)

    if not result_lists:
        return []

    fused = reciprocal_rank_fusion(result_lists, top_k=top_k)
    ids   = [r["incident_id"] for r in fused]

    cards = await fetch_incident_cards(ids, db)

    # Attach RRF scores
    score_map = {r["incident_id"]: r["rrf_score"] for r in fused}
    for card in cards:
        card["similarity_score"] = score_map.get(card["incident_id"], 0.0)

    return cards
