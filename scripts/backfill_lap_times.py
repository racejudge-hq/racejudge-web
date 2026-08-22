"""
Repair lap_features.time — it holds the session start on every lap.

`lap_features.time` is meant to be the moment the lap began, and it is what
places an incident on a lap. Every one of the 105,768 rows instead holds its
session's scheduled start: all 182 sessions have exactly one distinct value.

The cause is in `scripts/_backfill_telemetry.py`, which reads FastF1's
`LapStartDate` and falls back to the session start when it is NaT. FastF1 only
computes `LapStartDate` during the telemetry load, and the backfill loads with
`telemetry=False`, so `LapStartDate` is NaT on *every* lap and the fallback --
written for the occasional out-lap -- fired for all of them.

The lap offset was there the whole time. `LapStartTime` is populated on every
lap without telemetry; it is a timedelta from the timing feed's zero. FastF1
turns it absolute with `t0_date`, which is `max(Date - Time)` over the
telemetry streams. Fetching the `car_data` stream alone reproduces `t0_date`
exactly -- checked against a full telemetry load on 2024 Mexico R and Q and
2023 Miami R, all three identical to the millisecond -- so this pays for one
stream rather than the whole telemetry download, and

    time = t0_date + LapStartTime

reproduces FastF1's own `LapStartDate` to the millisecond.

That clock is the one incidents are on: `t0_date` comes from the timing feed's
UTC `Date`, the same feed race control messages are timestamped from. On
session 9625 the repaired laps span 20:03:34 -> 21:44:24, inside the session's
race control span of 19:08:01 -> 21:54:42, where the stored value was 20:00:00
throughout.

Real data only, and nothing is invented: a lap whose `LapStartTime` FastF1 does
not report, or a session whose `t0_date` cannot be computed, is left as it is
rather than given an approximation. The scheduled start is not used as a
fallback here -- that is the bug being repaired.

Idempotent: an UPDATE keyed on (session_key, driver_number, lap_number).

Usage:
    python scripts/backfill_lap_times.py --dry-run
    python scripts/backfill_lap_times.py
    python scripts/backfill_lap_times.py --session 9625
"""
from __future__ import annotations

import argparse
import os
import sys
import time as _time
import warnings
from datetime import UTC
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

warnings.filterwarnings("ignore")
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
import fastf1  # noqa: E402
from fastf1 import _api as fastf1_api  # noqa: E402

fastf1.logger.set_log_level("ERROR")
os.makedirs(ROOT / "data/fastf1_cache", exist_ok=True)
fastf1.Cache.enable_cache(str(ROOT / "data/fastf1_cache"))

DB = os.environ["DATABASE_URL"].replace("+asyncpg", "")

# sessions.session_type -> FastF1 identifiers, tried in order. The sprint
# qualifying session is named differently between the 2023 and 2024+ formats.
SESSION_CODES = {
    "practice_1": ["FP1"],
    "practice_2": ["FP2"],
    "practice_3": ["FP3"],
    "qualifying": ["Q"],
    "race": ["R"],
    "sprint": ["Sprint", "S"],
    "sprint_qualifying": ["Sprint Shootout", "SQ", "Sprint Qualifying", "SS"],
}

UPDATE = """
UPDATE lap_features SET time = %s
 WHERE session_key = %s AND driver_number = %s AND lap_number = %s
"""


def sessions_to_do(cur, season: int | None, single: int | None) -> list[tuple]:
    """(session_key, session_type, season, round_number) for sessions we hold laps for."""
    where = ["s.session_key IN (SELECT DISTINCT session_key FROM lap_features)"]
    params: list = []
    if single:
        where.append("s.session_key = %s")
        params.append(single)
    if season:
        where.append("e.season = %s")
        params.append(season)
    cur.execute(f"""
        SELECT s.session_key, s.session_type, e.season, e.round_number
          FROM sessions s JOIN events e USING (event_id)
         WHERE {' AND '.join(where)}
         ORDER BY e.season, e.round_number
    """, params)
    return cur.fetchall()


def load_session(season: int, round_number: int, session_type: str):
    """A loaded FastF1 session with laps, or None. Retries FastF1's rate limit."""
    for code in SESSION_CODES.get(session_type, []):
        for _ in range(4):
            try:
                s = fastf1.get_session(season, round_number, code)
                s.load(telemetry=False, weather=False, messages=False)
                if s.laps is not None and len(s.laps) > 0:
                    return s
                break
            except Exception as exc:  # noqa: BLE001
                if "RateLimit" in type(exc).__name__:
                    _time.sleep(45)  # let FastF1's sliding window recover
                    continue
                break
    return None


def t0_date_of(session):
    """FastF1's t0_date from the car_data stream alone, or None.

    `Session._calculate_t0_date` takes `max(Date - Time)` across the car and
    position streams -- the sample with the least feed delay. Either stream
    alone reaches the same maximum, so this fetches only one of the two.
    """
    for _ in range(4):
        try:
            car = fastf1_api.car_data(session.api_path)
            break
        except Exception as exc:  # noqa: BLE001
            if "RateLimit" in type(exc).__name__:
                _time.sleep(45)
                continue
            return None
    else:
        return None
    offsets = [max(d["Date"] - d["Time"]) for d in car.values() if len(d.get("Date", []))]
    if not offsets:
        return None
    return max(offsets).round("ms")


def time_rows(session_key: int, laps, t0) -> list[tuple]:
    """(time, session_key, driver_number, lap_number) for every lap FastF1 places."""
    rows = []
    for _, lap in laps.iterrows():
        lst, dn, ln = lap.get("LapStartTime"), lap.get("DriverNumber"), lap.get("LapNumber")
        if lst is None or pd.isna(lst) or ln is None or pd.isna(ln):
            continue
        try:
            driver_number = int(dn)
        except (TypeError, ValueError):
            continue
        # FastF1 works in naive UTC; lap_features.time is timestamptz.
        stamp = (pd.Timestamp(t0) + lst).to_pydatetime().replace(tzinfo=UTC)
        rows.append((stamp, session_key, driver_number, int(ln)))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Repair lap_features.time from FastF1")
    ap.add_argument("--season", type=int, help="Filter by season year")
    ap.add_argument("--session", type=int, help="Single session_key only")
    ap.add_argument("--dry-run", action="store_true", help="Report, write nothing")
    args = ap.parse_args()

    conn = psycopg2.connect(DB)
    cur = conn.cursor()
    todo = sessions_to_do(cur, args.season, args.session)
    print(f"{len(todo)} sessions to process", flush=True)

    ok = skipped = no_t0 = written = 0
    for i, (session_key, session_type, season, rnd) in enumerate(todo, 1):
        session = load_session(season, rnd, session_type)
        if session is None:
            skipped += 1
            print(f"[{i}/{len(todo)}] {session_key} {season} r{rnd} {session_type}: "
                  f"no FastF1 laps", flush=True)
            continue
        t0 = t0_date_of(session)
        if t0 is None:
            no_t0 += 1
            print(f"[{i}/{len(todo)}] {session_key} {season} r{rnd} {session_type}: "
                  f"no t0_date — left unchanged", flush=True)
            continue
        rows = time_rows(session_key, session.laps, t0)
        if rows and not args.dry_run:
            execute_batch(cur, UPDATE, rows, page_size=500)
            conn.commit()
        written += len(rows)
        ok += 1
        span = f"{min(r[0] for r in rows):%H:%M:%S}->{max(r[0] for r in rows):%H:%M:%S}" if rows else "-"
        print(f"[{i}/{len(todo)}] {session_key} {season} r{rnd} {session_type}: "
              f"{len(rows)} laps timed {span}", flush=True)

    print(f"\nDONE — sessions ok={ok} skipped={skipped} no_t0={no_t0}", flush=True)
    print(f"lap rows {'that would be ' if args.dry_run else ''}timed: {written}", flush=True)
    if args.dry_run:
        print("--dry-run: nothing written")
        return
    cur.execute("""SELECT count(*) FROM (
                     SELECT session_key FROM lap_features
                      GROUP BY session_key HAVING count(DISTINCT time) > 1) x""")
    varying = cur.fetchone()[0]
    cur.execute("SELECT count(DISTINCT session_key) FROM lap_features")
    print(f"sessions whose laps now differ in time: {varying}/{cur.fetchone()[0]}", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
