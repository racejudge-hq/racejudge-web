"""
Nightly BGE-M3 embedding flow — Phase 4.

Runs after ingest_flow to ensure new incidents get embeddings.
Also recomputes top-20 precedent links for newly embedded incidents.

Schedule: every Tuesday 03:00 UTC (after Monday ingest)
Manual trigger: prefect run deployment embedding-flow/prod

To deploy:
    prefect deploy packages/pipeline/flows/embedding_flow.py:embedding_flow \
        --name prod --cron "0 3 * * 2"
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

try:
    from prefect import flow, get_run_logger, task
    from prefect.artifacts import create_markdown_artifact
    _PREFECT = True
except ImportError:
    _PREFECT = False
    def flow(fn=None, **_):  # type: ignore[misc,no-redef]
        return fn if fn else lambda f: f
    def task(fn=None, **_):  # type: ignore[misc,no-redef]
        return fn if fn else lambda f: f
    def get_run_logger():  # type: ignore[misc,no-redef]
        return logging.getLogger(__name__)


@task(name="embed-incidents", retries=1, retry_delay_seconds=120)
def embed_incidents_task(batch_size: int = 64) -> dict:
    log = get_run_logger()
    from packages.pipeline.ml.embedder import backfill_embeddings

    log.info("Starting BGE-M3 embedding backfill (batch_size=%d)", batch_size)
    stats = backfill_embeddings(batch_size=batch_size)
    log.info("Embedding complete: %s", stats)
    return stats


@task(name="refresh-precedent-links", retries=1, retry_delay_seconds=60)
def refresh_precedent_links_task(top_k: int = 20) -> dict:
    """
    For every incident that was embedded or re-embedded, compute the
    top-k nearest neighbours via pgvector and write to precedent_links.
    """
    import os

    import psycopg2

    log = get_run_logger()

    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        log.warning("DATABASE_URL not set — skipping precedent link refresh")
        return {"refreshed": 0}

    conn = psycopg2.connect(database_url)
    cur  = conn.cursor()

    # Find incidents embedded today or without any precedent links
    # Administrative documents — power-unit tallies, drivers' meeting notes —
    # are not rulings and must not be stored as anyone's precedent, on either
    # side of the link. See migration 0015.
    cur.execute("""
        SELECT DISTINCT i.incident_id
        FROM incidents i
        JOIN decisions d ON i.doc_id = d.doc_id
        LEFT JOIN precedent_links pl ON i.incident_id = pl.incident_id
        WHERE i.embedding IS NOT NULL
          AND d.is_precedent IS NOT FALSE
          AND (
              pl.incident_id IS NULL
              OR i.embedded_at > NOW() - INTERVAL '2 days'
          )
        LIMIT 2000
    """)
    incident_ids = [r[0] for r in cur.fetchall()]
    log.info("Refreshing precedent links for %d incidents", len(incident_ids))

    refreshed = 0
    for iid in incident_ids:
        # Find top-k nearest by cosine similarity (excluding self)
        cur.execute("""
            SELECT candidate.incident_id,
                   1 - (i.embedding <=> candidate.embedding) AS score
            FROM incidents i
            CROSS JOIN LATERAL (
                SELECT c.incident_id, c.embedding
                FROM incidents c
                JOIN decisions cd ON c.doc_id = cd.doc_id
                WHERE c.incident_id != %s
                  AND c.embedding IS NOT NULL
                  AND cd.is_precedent IS NOT FALSE
                ORDER BY c.embedding <=> i.embedding
                LIMIT %s
            ) AS candidate
            WHERE i.incident_id = %s
        """, (iid, top_k, iid))
        neighbours = cur.fetchall()

        if not neighbours:
            continue

        # Upsert into precedent_links
        cur.execute("DELETE FROM precedent_links WHERE incident_id = %s", (iid,))
        for sim_id, score in neighbours:
            cur.execute("""
                INSERT INTO precedent_links (incident_id, similar_incident_id, similarity_score, link_type)
                VALUES (%s, %s, %s, 'semantic')
                ON CONFLICT DO NOTHING
            """, (iid, sim_id, score))

        refreshed += 1

    conn.commit()
    cur.close()
    conn.close()
    log.info("Refreshed precedent links for %d incidents", refreshed)
    return {"refreshed": refreshed}


@flow(name="embedding-flow", log_prints=True)
def embedding_flow(batch_size: int = 64, top_k: int = 20) -> dict:
    """
    Main embedding + precedent-link refresh flow.

    Args:
        batch_size: Embedding batch size for BGE-M3.
        top_k:      Number of nearest neighbours to store per incident.
    """
    log = get_run_logger()

    embed_stats = embed_incidents_task(batch_size=batch_size)
    link_stats  = refresh_precedent_links_task(top_k=top_k)

    summary = {
        "embedded":   embed_stats.get("embedded", 0),
        "skipped":    embed_stats.get("skipped", 0),
        "links_refreshed": link_stats.get("refreshed", 0),
        "run_at": datetime.now(UTC).isoformat(),
    }

    if _PREFECT:
        create_markdown_artifact(
            key="embedding-summary",
            markdown=f"""## Embedding Flow Summary
- **Newly embedded:** {summary['embedded']}
- **Skipped (empty text):** {summary['skipped']}
- **Precedent links refreshed:** {summary['links_refreshed']}
""",
        )

    log.info("Embedding flow complete: %s", summary)
    return summary


if __name__ == "__main__":
    import argparse
    import logging as _logging

    _logging.basicConfig(level=_logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--top-k",      type=int, default=20)
    args = parser.parse_args()
    result = embedding_flow(batch_size=args.batch_size, top_k=args.top_k)
    print(result)
