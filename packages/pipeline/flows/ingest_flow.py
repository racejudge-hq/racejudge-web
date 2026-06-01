"""
Prefect 3 ingestion flow — Phase 1.

Orchestrates:
  1. Scrape FIA season pages (Playwright)
  2. Download + parse PDFs (pdfplumber)
  3. Load records into Postgres via decisions table

Schedule: every Monday 09:00 UTC (post-race-weekend cleanup)
Manual trigger: prefect run deployment ingest-flow/prod

To deploy:
    prefect deploy packages/pipeline/flows/ingest_flow.py:ingest_flow \
        --name prod --cron "0 9 * * 1"
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

# Prefect imports are lazy so this file is importable without prefect installed
try:
    from prefect import flow, get_run_logger, task
    from prefect.artifacts import create_markdown_artifact
    _PREFECT = True
except ImportError:
    _PREFECT = False
    # Stubs so the module is importable during tests
    def flow(fn=None, **_):
        return fn if fn else lambda f: f
    def task(fn=None, **_):
        return fn if fn else lambda f: f
    def get_run_logger():
        return logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]
PARSED_JSONL = ROOT / "data" / "parsed" / "decisions.jsonl"


@task(retries=2, retry_delay_seconds=60, name="scrape-season")
def scrape_season_task(season: int, use_playwright: bool = True) -> list[dict]:
    """Scrape one FIA season and return new parsed records."""
    log = get_run_logger()
    from packages.pipeline.scrapers.fia_scraper import _load_hash_db, _save_hash_db, ingest_season

    ingested_hashes = _load_hash_db()
    log.info("Scraping season %d (%d hashes already ingested)", season, len(ingested_hashes))

    records = ingest_season(season, ingested_hashes, use_playwright=use_playwright)

    if records:
        # Append to JSONL
        with PARSED_JSONL.open("a", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        _save_hash_db(ingested_hashes)

    log.info("Season %d: %d new records", season, len(records))
    return records


@task(name="load-to-postgres")
def load_to_postgres_task(records: list[dict]) -> int:
    """Upsert parsed decision records into Postgres decisions table."""
    if not records:
        return 0

    log = get_run_logger()
    import os
    try:
        import psycopg2
    except ImportError:
        log.warning("psycopg2 not installed — skipping Postgres load")
        return 0

    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        log.warning("DATABASE_URL not set — skipping Postgres load")
        return 0

    conn = psycopg2.connect(database_url)
    cur = conn.cursor()
    inserted = 0

    for r in records:
        cur.execute(
            """
            INSERT INTO decisions
                (doc_id, sha256_hash, title, pdf_url, r2_key, season,
                 published_at, raw_text, char_count, needs_ocr,
                 parser_version, parsed_at)
            VALUES (%(doc_id)s, %(sha256_hash)s, %(title)s, %(pdf_url)s,
                    %(r2_key)s, %(season)s, %(published_at)s, %(raw_text)s,
                    %(char_count)s, %(needs_ocr)s, %(parser_version)s,
                    %(parsed_at)s)
            ON CONFLICT (sha256_hash) DO NOTHING
            """,
            r,
        )
        inserted += cur.rowcount

    conn.commit()
    cur.close()
    conn.close()
    log.info("Inserted %d records into Postgres", inserted)
    return inserted


@flow(name="ingest-flow", log_prints=True)
def ingest_flow(
    seasons: list[int] | None = None,
    use_playwright: bool = True,
) -> dict:
    """
    Main ingestion flow.  Scrapes FIA seasons and loads into Postgres.

    Args:
        seasons: list of calendar years to scrape. Defaults to current year.
        use_playwright: use headless browser for season filtering (recommended).
    """
    log = get_run_logger()

    if not seasons:
        seasons = [datetime.now(UTC).year]

    total_new = 0
    total_pg  = 0

    for season in seasons:
        records = scrape_season_task(season, use_playwright=use_playwright)
        pg_count = load_to_postgres_task(records)
        total_new += len(records)
        total_pg  += pg_count

    summary = {
        "seasons": seasons,
        "new_records": total_new,
        "postgres_inserted": total_pg,
        "run_at": datetime.now(UTC).isoformat(),
    }

    if _PREFECT:
        create_markdown_artifact(
            key="ingest-summary",
            markdown=f"""## Ingest Summary
- **Seasons:** {seasons}
- **New records:** {total_new}
- **Postgres rows inserted:** {total_pg}
""",
        )

    log.info("Ingest complete: %s", summary)
    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, action="append", dest="seasons")
    parser.add_argument("--no-playwright", action="store_true")
    args = parser.parse_args()
    result = ingest_flow(seasons=args.seasons, use_playwright=not args.no_playwright)
    print(result)
