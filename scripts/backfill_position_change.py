"""
Derive incidents.position_change from lap_features.position.

`position_change` is read by the API and by the penalty predictor and has never
held a value. Migration 0020 added `lap_features.position` from FastF1; this
turns it into the per-incident figure.

Definition, since nothing previously fixed one:

    position_change = position at the end of the lap before the incident
                    - position at the end of the incident lap

so a positive value means the car moved forward across the incident. A driver
who fell from 4th to 7th scores -3.

Only rulings against exactly one car are computed. "The car the ruling is
against" is the whole basis of the sign, and a deleted-lap-times document
covering eighteen drivers has no single subject, so those are left NULL rather
than given a number that means nothing.

The incident is placed in the session by the time the document states. Where
the document states none, the earliest linked race control message stands in —
race control notes an incident within minutes, which is inside a lap.

Nothing is invented: an incident whose lap, neighbours or positions are missing
from FastF1's timing is left NULL.

Usage:
    python scripts/backfill_position_change.py --dry-run
    python scripts/backfill_position_change.py
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

DB = os.environ["DATABASE_URL"].replace("+asyncpg", "")

# The ruling's subject, the moment to place it at, and the session's laps.
# COALESCE lets a linked race control message stand in for a document that
# states no time; the join table is the only source for that since migration
# 0018 moved the links off race_control_messages.incident_id.
CANDIDATES = """
SELECT i.incident_id,
       i.session_key,
       (i.drivers -> 0 ->> 'number')::int AS car,
       COALESCE(i.incident_time,
                (SELECT min(r.date) FROM incident_race_control l
                   JOIN race_control_messages r ON r.message_id = l.message_id
                  WHERE l.incident_id = i.incident_id)) AS at
  FROM incidents i
 WHERE jsonb_array_length(i.drivers) = 1
   AND i.drivers -> 0 ->> 'number' IS NOT NULL
   AND i.session_key IN (SELECT DISTINCT session_key FROM lap_features
                          WHERE position IS NOT NULL)
"""

LAPS = """
SELECT lap_number, time, position
  FROM lap_features
 WHERE session_key = %s AND driver_number = %s AND position IS NOT NULL
 ORDER BY lap_number
"""


def change_for(laps: list[tuple], at) -> tuple[int, int] | None:
    """(position_change, incident lap) or None when the timing cannot place it.

    `lap_features.time` is the lap's start, so the lap in progress at `at` is
    the last one that started at or before it.
    """
    started = [row for row in laps if row[1] is not None and row[1] <= at]
    if not started:
        return None
    lap_number = started[-1][0]
    by_lap = {row[0]: row[2] for row in laps}
    before, after = by_lap.get(lap_number - 1), by_lap.get(lap_number)
    if before is None or after is None:
        return None  # first lap of the session, or a gap in the timing
    return before - after, lap_number


def main() -> None:
    ap = argparse.ArgumentParser(description="Derive incidents.position_change")
    ap.add_argument("--dry-run", action="store_true", help="Report, write nothing")
    args = ap.parse_args()

    conn = psycopg2.connect(DB)
    cur = conn.cursor()
    cur.execute(CANDIDATES)
    rows = cur.fetchall()
    print(f"{len(rows)} single-driver rulings in sessions that hold positions", flush=True)

    lap_cache: dict[tuple[int, int], list[tuple]] = {}
    updates: list[tuple[int, str]] = []
    no_anchor = no_placement = 0
    for incident_id, session_key, car, at in rows:
        if at is None:
            no_anchor += 1
            continue
        key = (session_key, car)
        if key not in lap_cache:
            cur.execute(LAPS, key)
            lap_cache[key] = cur.fetchall()
        result = change_for(lap_cache[key], at)
        if result is None:
            no_placement += 1
            continue
        updates.append((result[0], incident_id))

    print(f"  computed              : {len(updates)}")
    print(f"  no time to place them : {no_anchor}")
    print(f"  timing could not place: {no_placement}")
    spread = Counter(v for v, _ in updates)
    print("  distribution:", ", ".join(
        f"{k:+d}:{n}" for k, n in sorted(spread.items())[:14]))

    if args.dry_run:
        print("\n--dry-run: nothing written")
        return

    cur.executemany(
        "UPDATE incidents SET position_change = %s WHERE incident_id = %s", updates
    )
    conn.commit()
    cur.execute("SELECT count(*) FROM incidents WHERE position_change IS NOT NULL")
    print(f"\nincidents.position_change now filled on {cur.fetchone()[0]} rows")
    conn.close()


if __name__ == "__main__":
    main()
