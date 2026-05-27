"""
Load parsed decisions from data/parsed/decisions.jsonl into Postgres.

Run after:
  1. psql $DATABASE_URL -f packages/db/schema.sql   (create tables)
  2. python scripts/load_jsonl_to_db.py              (bulk insert)

Idempotent — skips rows whose sha256_hash already exists.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JSONL = ROOT / "data" / "parsed" / "decisions.jsonl"


def main() -> None:
    try:
        import psycopg2
    except ImportError:
        print("psycopg2 not installed — run: pip install psycopg2-binary")
        sys.exit(1)

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL not set. Copy .env.example → .env and fill in your Neon URL.")
        sys.exit(1)

    if not JSONL.exists():
        print(f"No decisions.jsonl found at {JSONL}. Run the scraper first.")
        sys.exit(1)

    records = [json.loads(l) for l in JSONL.read_text().splitlines() if l.strip()]
    print(f"Loading {len(records)} records into Postgres...")

    conn = psycopg2.connect(database_url)
    cur = conn.cursor()

    inserted = skipped = 0
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
        if cur.rowcount:
            inserted += 1
        else:
            skipped += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"Done. Inserted: {inserted}, skipped (already existed): {skipped}")


if __name__ == "__main__":
    main()
