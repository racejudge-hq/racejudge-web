"""
Fill incidents.video_refs from the evidence the stewards state they reviewed.

`video_refs` is read by the API and has never held a value. Its name suggests
links, and links are the one thing the corpus cannot supply: not one of the
1,606 decision documents contains a URL of any kind. Constructing F1TV or
YouTube addresses from the event and lap would be inventing them, so nothing of
the sort is done here.

What the documents do carry is the stewards' own account of the evidence, in a
sentence written to a near-fixed formula:

    "The Stewards reviewed positioning/marshalling system data, video, timing,
     team radio and in-car video evidence."

803 documents carry such a clause. `extract_video_refs` reads the vision items
out of it -- video, in-car video, CCTV -- and leaves telemetry, timing, GPS,
team radio and positioning data alone, because those are not what this column
is for. That is a real reference to video, taken from the ruling itself like
every other extracted field.

Real data only: every value is read from the document text. A document that
names no vision evidence is left NULL rather than given an empty list, so
"the stewards reviewed none" stays distinguishable from "this document does not
say".

Idempotent: an UPDATE keyed on doc_id, so re-running rewrites the same values.

Usage:
    python scripts/backfill_video_refs.py --dry-run
    python scripts/backfill_video_refs.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_batch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from packages.pipeline.parsers.decision_parser import extract_video_refs  # noqa: E402

DB = os.environ["DATABASE_URL"].replace("+asyncpg", "")

# The body only. The evidence sentence is always in the Reason; a title never
# states the evidence, and the reviewing verb appears in the titles of
# review-procedure notices, which examined nothing.
SOURCE = """
SELECT i.incident_id, d.raw_text
  FROM incidents i JOIN decisions d ON d.doc_id = i.doc_id
 WHERE d.raw_text IS NOT NULL
"""

UPDATE = "UPDATE incidents SET video_refs = %s WHERE incident_id = %s"


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill incidents.video_refs")
    ap.add_argument("--dry-run", action="store_true", help="Report, write nothing")
    args = ap.parse_args()

    conn = psycopg2.connect(DB)
    cur = conn.cursor()
    cur.execute(SOURCE)
    rows = cur.fetchall()
    print(f"{len(rows)} incidents with document text", flush=True)

    updates: list[tuple[str, str]] = []
    combos: Counter = Counter()
    for incident_id, raw_text in rows:
        refs = extract_video_refs(raw_text)
        if not refs:
            continue
        combos[tuple(refs)] += 1
        updates.append((json.dumps(refs), incident_id))

    print(f"  naming vision evidence: {len(updates)}")
    print(f"  naming none            : {len(rows) - len(updates)}")
    for combo, n in combos.most_common():
        print(f"    {n:5d}  {list(combo)}")

    if args.dry_run:
        print("\n--dry-run: nothing written")
        return

    execute_batch(cur, UPDATE, updates, page_size=500)
    conn.commit()
    cur.execute("SELECT count(*) FROM incidents WHERE video_refs IS NOT NULL")
    print(f"\nincidents.video_refs now filled on {cur.fetchone()[0]} rows", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
