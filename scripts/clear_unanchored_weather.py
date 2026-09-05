"""
Clear incidents.weather_context where nothing says when the incident happened.

`weather_context` asserts a fact about a moment -- "it was 28.5C and dry" -- so
it is only meaningful if the moment is known. v16 anchored it on the earliest
linked race control message, failing that the time the decision states, and
never on publication time, which is the FIA's paperwork clock and can be hours
or a day after the flag. 44 rows built on publication time were cleared then.

11 survived, because that clearing keyed off incidents whose *time* was wrong
rather than incidents that have no time at all. These have no `incident_time`
and no linked race control message: nothing in the database says when they
happened, so their weather cannot be right except by luck.

`WeatherLinker.get_weather_at_incident` returns None without an anchor, so the
current code cannot recreate them -- this is a one-off cleanup of rows written
before that rule existed. It is idempotent and safe to re-run; a clean database
reports 0 and writes nothing.

Usage:
    python scripts/clear_unanchored_weather.py --dry-run
    python scripts/clear_unanchored_weather.py
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

DB = os.environ["DATABASE_URL"].replace("+asyncpg", "")

# An incident is anchored by the time it states, or by a race control message
# linked to it. The join table is the only source of the second since 0018.
UNANCHORED = """
SELECT i.incident_id, d.title
  FROM incidents i
  JOIN decisions d ON d.doc_id = i.doc_id
 WHERE i.weather_context IS NOT NULL
   AND i.incident_time IS NULL
   AND NOT EXISTS (SELECT 1 FROM incident_race_control l
                    WHERE l.incident_id = i.incident_id)
 ORDER BY d.title
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Clear weather with no anchor")
    ap.add_argument("--dry-run", action="store_true", help="Report, write nothing")
    args = ap.parse_args()

    conn = psycopg2.connect(DB)
    cur = conn.cursor()
    cur.execute(UNANCHORED)
    rows = cur.fetchall()

    print(f"{len(rows)} incidents hold weather with nothing to anchor it to")
    for _, title in rows:
        print(f"  {title[:72]}")

    if not rows:
        return
    if args.dry_run:
        print("\n--dry-run: nothing written")
        return

    cur.execute(
        "UPDATE incidents SET weather_context = NULL WHERE incident_id = ANY(%s)",
        ([r[0] for r in rows],),
    )
    conn.commit()
    cur.execute("SELECT count(*) FROM incidents WHERE weather_context IS NOT NULL")
    print(f"\nweather_context now on {cur.fetchone()[0]} incidents, all anchored")
    conn.close()


if __name__ == "__main__":
    main()
