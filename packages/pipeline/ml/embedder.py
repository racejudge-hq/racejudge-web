"""
BGE-M3 batch embedder — Phase 4.

Computes 1024-dim sentence embeddings for all incidents that have
reasoning_text but no embedding, then writes them back to Postgres.

Usage (one-shot backfill):
    python -m packages.pipeline.ml.embedder --batch-size 64

The embedder is also called from embedding_flow.py nightly.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

log = logging.getLogger(__name__)

EMBED_MODEL  = os.environ.get("EMBED_MODEL", "BAAI/bge-m3")
EMBED_DIM    = 1024
DEFAULT_BATCH = 64


def _get_model():
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(EMBED_MODEL)
        log.info("Loaded %s", EMBED_MODEL)
        return model
    except ImportError as exc:
        raise ImportError(
            "sentence-transformers not installed. "
            "Uncomment it in requirements.txt and run: pip install -r requirements.txt"
        ) from exc


def _embed_texts(model, texts: list[str]) -> list[list[float]]:
    vecs = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False,
        batch_size=32,
    )
    return [v.tolist() for v in vecs]


def backfill_embeddings(batch_size: int = DEFAULT_BATCH) -> dict[str, Any]:
    """
    Embed all incidents that are missing an embedding.
    Writes vectors directly to Postgres via psycopg2 (sync, for CLI use).
    Returns a stats dict.
    """
    import psycopg2

    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL env var not set")

    model = _get_model()
    conn  = psycopg2.connect(database_url)
    cur   = conn.cursor()

    # Fetch incidents without embeddings
    cur.execute("""
        SELECT incident_id, reasoning_text
        FROM incidents
        WHERE embedding IS NULL AND reasoning_text != ''
        ORDER BY created_at
    """)
    rows = cur.fetchall()
    log.info("Found %d incidents without embeddings", len(rows))

    if not rows:
        cur.close()
        conn.close()
        return {"embedded": 0, "skipped": 0}

    embedded = 0
    skipped  = 0
    now      = datetime.now(UTC).isoformat()

    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        ids   = [r[0] for r in batch]
        texts = [r[1] for r in batch]

        valid = [(iid, t) for iid, t in zip(ids, texts, strict=True) if t and t.strip()]
        if not valid:
            skipped += len(batch)
            continue

        valid_ids, valid_texts = zip(*valid, strict=False)
        vecs = _embed_texts(model, list(valid_texts))

        for iid, vec in zip(valid_ids, vecs, strict=True):
            cur.execute("""
                UPDATE incidents
                SET embedding = %s::vector,
                    embedding_model = %s,
                    embedded_at     = %s
                WHERE incident_id = %s
            """, (str(vec), EMBED_MODEL, now, iid))

        conn.commit()
        embedded += len(valid)
        log.info("Embedded %d/%d incidents", i + len(batch), len(rows))

    cur.close()
    conn.close()
    return {"embedded": embedded, "skipped": skipped}


def embed_single(text: str, model=None) -> list[float] | None:
    """Embed a single text string. Used by the precedents router for query embedding."""
    if model is None:
        try:
            model = _get_model()
        except ImportError:
            return None
    vecs = _embed_texts(model, [text])
    return vecs[0]


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Backfill BGE-M3 embeddings")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH)
    args = parser.parse_args()

    stats = backfill_embeddings(batch_size=args.batch_size)
    print(f"Done — {stats}")
