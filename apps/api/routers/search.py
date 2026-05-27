"""
Full-text search endpoint — Phase 1 (keyword) → Phase 4 (BGE-M3 + BM25 RRF).

Current implementation: simple TF-style keyword scoring over raw_text.
Phase 4 will replace this with pgvector ANN + BM25 Reciprocal Rank Fusion.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from apps.api.routers.decisions import _load_decisions

router = APIRouter(tags=["search"])


class SearchResult(BaseModel):
    doc_id: str
    title: str
    season: int
    published_at: str | None
    score: float
    snippet: str


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _snippet(text: str, query_tokens: list[str], window: int = 200) -> str:
    """Return a snippet around the first query token match."""
    lower = text.lower()
    for tok in query_tokens:
        idx = lower.find(tok)
        if idx != -1:
            start = max(0, idx - 60)
            end   = min(len(text), idx + window)
            raw = text[start:end].strip()
            return ("…" if start > 0 else "") + raw + ("…" if end < len(text) else "")
    return text[:window].strip() + "…"


def _bm25_score(
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


@router.get("/search", response_model=list[SearchResult])
async def search_decisions(
    q: Annotated[str, Query(description="Search query", min_length=2)],
    season: Annotated[int | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[dict]:
    """
    BM25 keyword search over decision titles and raw text.
    Phase 4 replaces this with hybrid pgvector + BM25 RRF.
    """
    records = _load_decisions()
    if season:
        records = [r for r in records if r.get("season") == season]

    if not records:
        return []

    # Build corpus
    query_tokens = _tokenize(q)
    if not query_tokens:
        return []

    tokenized_docs = [
        _tokenize(r.get("title", "") + " " + r.get("raw_text", ""))
        for r in records
    ]

    # IDF: document frequency per token
    doc_freq: dict[str, int] = Counter()
    for tokens in tokenized_docs:
        for tok in set(tokens):
            doc_freq[tok] += 1

    avg_dl = sum(len(t) for t in tokenized_docs) / max(len(tokenized_docs), 1)
    num_docs = len(records)

    # Score each document
    scored = []
    for rec, doc_tokens in zip(records, tokenized_docs):
        score = _bm25_score(query_tokens, doc_tokens, doc_freq, num_docs, avg_dl)
        if score > 0:
            scored.append((score, rec))

    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, rec in scored[:limit]:
        results.append({
            "doc_id":       rec["doc_id"],
            "title":        rec["title"],
            "season":       rec["season"],
            "published_at": rec.get("published_at"),
            "score":        round(score, 4),
            "snippet":      _snippet(rec.get("raw_text", rec.get("title", "")), query_tokens),
        })
    return results
