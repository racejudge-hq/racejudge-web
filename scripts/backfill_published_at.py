"""
Fill decisions.published_at_utc from the raw string beside it.

`published_at` is TEXT holding whatever the FIA listing page's date element
carried: `Published on08.10.23 20:58CET` on 1,447 rows and a bare
`07.12.25 15:59` on the other 159. Migration 0022 adds a typed column next to
it; this parses the strings into it. The raw text is not touched -- it is what
the source said, and a parse that later proves wrong must stay re-derivable.

Both shapes are the same clock, measured rather than assumed: against the 642
incidents whose UTC time is known, the two have the same publication lag
(median 120 and 138 minutes) and neither yields a document published before the
incident it describes.

"CET" on that page means Paris local time. See `parse_published_at` and
migration 0022 for the measurement that settles it.

Usage:
    python scripts/backfill_published_at.py --dry-run
    python scripts/backfill_published_at.py
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from packages.pipeline.scrapers.fia_scraper import parse_published_at  # noqa: E402

DB = os.environ["DATABASE_URL"].replace("+asyncpg", "")


def main() -> None:
    ap = argparse.ArgumentParser(description="Fill decisions.published_at_utc")
    ap.add_argument("--dry-run", action="store_true", help="Report, write nothing")
    args = ap.parse_args()

    conn = psycopg2.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT doc_id, published_at, season FROM decisions")
    rows = cur.fetchall()

    updates: list[tuple[object, str]] = []
    unparsed: Counter[str] = Counter()
    disagrees = 0
    for doc_id, raw, season in rows:
        parsed = parse_published_at(raw)
        if parsed is None:
            unparsed[(raw or "")[:40]] += 1
            continue
        # A document is published during its own season or shortly after; a
        # parse that lands in a different year is a misread, not a late filing.
        if season and not (season <= parsed.year <= season + 1):
            disagrees += 1
            continue
        updates.append((parsed, doc_id))

    print(f"{len(rows)} decisions")
    print(f"  parsed                     : {len(updates)}")
    print(f"  no date in the raw string  : {sum(unparsed.values())}")
    for raw, n in unparsed.most_common(5):
        print(f"      {raw!r} x{n}")
    print(f"  parsed year != season      : {disagrees}")

    if args.dry_run:
        print("\n--dry-run: nothing written")
        return

    cur.executemany(
        "UPDATE decisions SET published_at_utc = %s WHERE doc_id = %s", updates
    )
    conn.commit()
    cur.execute("""
        SELECT count(published_at_utc), min(published_at_utc), max(published_at_utc)
          FROM decisions
    """)
    filled, lo, hi = cur.fetchone()
    print(f"\npublished_at_utc filled on {filled} decisions, {lo} .. {hi}")
    conn.close()


if __name__ == "__main__":
    main()
