"""
Fill lap_features.position from FastF1 — the source for incidents.position_change.

`scripts/_backfill_telemetry.py` already loads every session's FastF1 lap table
to store lap and sector times; that same table carries a `Position` column that
was never selected. This reads it for the sessions lap_features already holds
and updates them in place, so no lap row is inserted or deleted here.

Sessions are resolved through the local `sessions`/`events` tables rather than
the OpenF1 sessions endpoint, so the job does not depend on OpenF1 being
reachable — FastF1 reads the F1 timing archive directly.

Real data only: every value comes from FastF1's official timing feed.
Idempotent: an UPDATE keyed on (session_key, driver_number, lap_number), so
re-running rewrites the same values rather than duplicating anything.

Usage:
    python scripts/backfill_lap_positions.py                # every session held
    python scripts/backfill_lap_positions.py --season 2024
    python scripts/backfill_lap_positions.py --session 9625
    python scripts/backfill_lap_positions.py --missing-only # skip sessions already filled
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import warnings
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
UPDATE lap_features SET position = %s
 WHERE session_key = %s AND driver_number = %s AND lap_number = %s
"""


def sessions_to_do(cur, season: int | None, single: int | None,
                   missing_only: bool) -> list[tuple]:
    """(session_key, session_type, season, round_number) for sessions we hold laps for."""
    where = ["s.session_key IN (SELECT DISTINCT session_key FROM lap_features)"]
    params: list = []
    if single:
        where.append("s.session_key = %s")
        params.append(single)
    if season:
        where.append("e.season = %s")
        params.append(season)
    if missing_only:
        where.append("""s.session_key NOT IN (
            SELECT DISTINCT session_key FROM lap_features WHERE position IS NOT NULL)""")
    cur.execute(f"""
        SELECT s.session_key, s.session_type, e.season, e.round_number
          FROM sessions s JOIN events e USING (event_id)
         WHERE {' AND '.join(where)}
         ORDER BY e.season, e.round_number
    """, params)
    return cur.fetchall()


def load_laps(season: int, round_number: int, session_type: str):
    """FastF1 laps for one session, or None. Retries FastF1's rate limit."""
    for code in SESSION_CODES.get(session_type, []):
        for _ in range(4):
            try:
                s = fastf1.get_session(season, round_number, code)
                s.load(telemetry=False, weather=False, messages=False)
                laps = s.laps
                if laps is not None and len(laps) > 0:
                    return laps
                break
            except Exception as exc:  # noqa: BLE001
                if "RateLimit" in type(exc).__name__:
                    time.sleep(45)  # let FastF1's sliding window recover
                    continue
                break
    return None


def position_rows(session_key: int, laps) -> list[tuple]:
    """(position, session_key, driver_number, lap_number) for every lap that has one."""
    if "Position" not in laps.columns:
        return []
    rows = []
    for _, lap in laps.iterrows():
        pos, dn, ln = lap.get("Position"), lap.get("DriverNumber"), lap.get("LapNumber")
        if pos is None or pd.isna(pos) or ln is None or pd.isna(ln):
            continue
        try:
            driver_number = int(dn)
        except (TypeError, ValueError):
            continue
        rows.append((int(pos), session_key, driver_number, int(ln)))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill lap_features.position from FastF1")
    ap.add_argument("--season", type=int, help="Filter by season year")
    ap.add_argument("--session", type=int, help="Single session_key only")
    ap.add_argument("--missing-only", action="store_true",
                    help="Skip sessions that already hold any position")
    args = ap.parse_args()

    conn = psycopg2.connect(DB)
    cur = conn.cursor()
    todo = sessions_to_do(cur, args.season, args.session, args.missing_only)
    print(f"{len(todo)} sessions to process", flush=True)

    ok = skipped = updated = 0
    for i, (session_key, session_type, season, rnd) in enumerate(todo, 1):
        laps = load_laps(season, rnd, session_type)
        if laps is None:
            skipped += 1
            print(f"[{i}/{len(todo)}] {session_key} {season} r{rnd} {session_type}: "
                  f"no FastF1 laps", flush=True)
            continue
        rows = position_rows(session_key, laps)
        if rows:
            execute_batch(cur, UPDATE, rows, page_size=500)
            conn.commit()
            updated += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        ok += 1
        print(f"[{i}/{len(todo)}] {session_key} {season} r{rnd} {session_type}: "
              f"{len(rows)} laps positioned", flush=True)

    cur.execute("SELECT count(*) FROM lap_features WHERE position IS NOT NULL")
    filled = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM lap_features")
    total = cur.fetchone()[0]
    conn.close()
    print(f"\nDONE — sessions ok={ok} skipped={skipped}", flush=True)
    print(f"lap_features.position filled on {filled}/{total} laps", flush=True)


if __name__ == "__main__":
    main()
