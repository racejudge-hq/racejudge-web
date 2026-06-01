"""
Seed FIA guidelines into the database.

Usage:
    DATABASE_URL=postgresql://... python scripts/seed_guidelines.py
    # Or with a PDF:
    DATABASE_URL=postgresql://... python scripts/seed_guidelines.py \
        --pdf path/to/penalty_guidelines_2025.pdf \
        --doc-name "FIA Penalty Guidelines 2025" \
        --date 2025-05-14

Falls back to hardcoded seed data if no PDF provided.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from packages.pipeline.parsers.guidelines_parser import (  # noqa: E402
    get_seed_guidelines,
    guidelines_to_dicts,
    parse_guidelines_pdf,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed FIA guidelines into Postgres")
    parser.add_argument("--pdf", type=Path, help="Path to guidelines PDF")
    parser.add_argument("--doc-name", help="Document name override")
    parser.add_argument("--date", help="Effective date (YYYY-MM-DD)")
    args = parser.parse_args()

    if args.pdf:
        rows = parse_guidelines_pdf(args.pdf, args.doc_name, args.date)
    else:
        print("No PDF provided — using hardcoded seed data.")
        rows = get_seed_guidelines()

    dicts = guidelines_to_dicts(rows)
    print(f"Seeding {len(dicts)} guideline rows...")

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set — printing rows instead:\n")
        for row in dicts:
            print(f"  [{row['article_number']}] {row['article_text'][:60]}")
            print(f"    penalty: {row['recommended_penalty']}")
        return

    try:
        import psycopg2
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()

        inserted = 0
        skipped = 0
        for row in dicts:
            cur.execute(
                """
                INSERT INTO guidelines
                  (document_name, section, article_number, article_text,
                   recommended_penalty, effective_date)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (document_name, article_number) DO NOTHING
                """,
                (
                    row["document_name"], row["section"], row["article_number"],
                    row["article_text"], row["recommended_penalty"], row["effective_date"],
                ),
            )
            if cur.rowcount:
                inserted += 1
            else:
                skipped += 1

        conn.commit()
        cur.close()
        conn.close()
        print(f"Done. Inserted: {inserted}, Skipped (already exist): {skipped}")
    except ImportError:
        print("psycopg2 not installed. Run: pip install psycopg2-binary")
        sys.exit(1)


if __name__ == "__main__":
    main()
