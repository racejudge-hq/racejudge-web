"""
Part 4 — Telemetry backfill into lap_features (real FastF1 timing data).

For every distinct OpenF1 session referenced by an incident (2023+), load the
matching FastF1 session and write per-lap timing features (lap/sector times,
speed-trap speeds, tyre compound + life, personal-best flag).

Real data only: every row comes straight from FastF1's official timing feed.
Idempotent: sessions already present in lap_features are skipped, so the job can
be re-run / resumed safely. Writes via psycopg2 (no ORM) to avoid type drift.
"""
from __future__ import annotations

import os
import time
import uuid
import warnings
from datetime import UTC, datetime

import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch

warnings.filterwarnings("ignore")
from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env")
import fastf1  # noqa: E402
from fastf1 import _api as fastf1_api  # noqa: E402

fastf1.logger.set_log_level("ERROR")
os.makedirs("data/fastf1_cache", exist_ok=True)
fastf1.Cache.enable_cache("data/fastf1_cache")

import requests  # noqa: E402

DB = os.environ["DATABASE_URL"]

# OpenF1 session_name -> FastF1 session identifiers (tried in order; the sprint
# "shootout"/"qualifying" name differs between the 2023 and 2024+ formats).
SESSION_CODES = {
    "Practice 1": ["FP1"], "Practice 2": ["FP2"], "Practice 3": ["FP3"],
    "Qualifying": ["Q"], "Race": ["R"], "Sprint": ["Sprint", "S"],
    "Sprint Qualifying": ["Sprint Shootout", "SQ", "Sprint Qualifying", "SS"],
    "Sprint Shootout": ["Sprint Shootout", "SS", "Sprint Qualifying", "SQ"],
}


def _ms(td) -> int | None:
    if td is None or pd.isna(td):
        return None
    return int(td.total_seconds() * 1000)


def _num(v) -> float | None:
    if v is None or pd.isna(v):
        return None
    return float(v)


def _ts(v) -> datetime | None:
    if v is None or pd.isna(v):
        return None
    dt = pd.Timestamp(v).to_pydatetime()
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def session_meta(session_key: int) -> dict | None:
    r = requests.get("https://api.openf1.org/v1/sessions",
                     params={"session_key": session_key}, timeout=30)
    rows = r.json()
    return rows[0] if rows else None


def load_fastf1(meta: dict):
    """Resolve a FastF1 session from OpenF1 metadata, trying several GP keys.

    Returns (session, laps) on success, else (None, last_error). `laps` is
    accessed *inside* the try so a partial load (which leaves laps unloaded and
    raises DataNotLoadedError on access) falls through to the next candidate
    instead of crashing the caller.
    """
    year = meta["year"]
    codes = SESSION_CODES.get(meta.get("session_name", ""), [meta.get("session_name")])
    gps = [g for g in (meta.get("location"), meta.get("country_name"),
                       meta.get("circuit_short_name")) if g]
    last_err = None
    for code in codes:
        for gp in gps:
            for _ in range(4):  # retry transient fetch / rate-limit errors
                try:
                    s = fastf1.get_session(year, gp, code)
                    s.load(telemetry=False, weather=False, messages=False)
                    laps = s.laps
                    if laps is not None and len(laps) > 0:
                        return s, laps
                    break  # loaded but empty — try next gp key
                except Exception as e:  # noqa: BLE001
                    last_err = e
                    name = type(e).__name__
                    if "RateLimit" in name:
                        time.sleep(45)  # let FastF1's sliding window recover
                        continue        # retry same gp/code
                    if isinstance(e, ValueError):
                        break            # invalid identifier — try next code/gp
                    break                # other transient — try next gp
    return None, last_err


def t0_from_car_data(session):
    """FastF1's t0_date without paying for the whole telemetry load, or None.

    `Session._calculate_t0_date` is `max(Date - Time)` over the car and position
    streams — the sample with the least feed delay. Either stream alone reaches
    the same maximum, so only one is fetched. See scripts/backfill_lap_times.py.
    """
    try:
        car = fastf1_api.car_data(session.api_path)
    except Exception:  # noqa: BLE001
        return None
    offsets = [max(d["Date"] - d["Time"]) for d in car.values() if len(d.get("Date", []))]
    return max(offsets).round("ms") if offsets else None


def lap_rows(session_key: int, laps, t0_date, fallback_start) -> list[tuple]:
    rows = []
    for _, lap in laps.iterrows():
        # LapStartDate is NaT unless the telemetry was loaded, which this script
        # does not do — so it is NaT on every lap, not just the odd out-lap, and
        # the session-start fallback this once had wrote the scheduled start
        # into all 105,768 rows. LapStartTime is always present; t0_date turns
        # it absolute. A lap FastF1 cannot place is left NULL (migration 0021)
        # rather than given a timestamp that merely looks like one.
        ts = _ts(lap.get("LapStartDate"))
        if ts is None and t0_date is not None:
            lst = lap.get("LapStartTime")
            if lst is not None and not pd.isna(lst):
                ts = _ts(pd.Timestamp(t0_date) + lst)
        dn = lap.get("DriverNumber")
        try:
            driver_number = int(dn) if dn not in (None, "") and not pd.isna(dn) else None
        except (ValueError, TypeError):
            driver_number = None
        ln = lap.get("LapNumber")
        lap_number = int(ln) if ln is not None and not pd.isna(ln) else None
        # driver_number, lap_number, is_personal_best are NOT NULL in lap_features
        if driver_number is None or lap_number is None:
            continue
        tl = lap.get("TyreLife")
        tyre_life = int(tl) if tl is not None and not pd.isna(tl) else None
        pb = lap.get("IsPersonalBest")
        is_pb = bool(pb) if pb is not None and not pd.isna(pb) else False
        comp = lap.get("Compound")
        compound = comp if isinstance(comp, str) and comp not in ("", "nan") else None
        rows.append((
            str(uuid.uuid4()),
            ts,
            session_key,
            driver_number,
            lap_number,
            _ms(lap.get("LapTime")),
            _ms(lap.get("Sector1Time")),
            _ms(lap.get("Sector2Time")),
            _ms(lap.get("Sector3Time")),
            _num(lap.get("SpeedI1")),
            _num(lap.get("SpeedI2")),
            _num(lap.get("SpeedFL")),
            _num(lap.get("SpeedST")),
            compound,
            tyre_life,
            is_pb,
        ))
    return rows


INSERT = """
INSERT INTO lap_features
  (id, time, session_key, driver_number, lap_number, lap_time_ms,
   sector1_ms, sector2_ms, sector3_ms, speed_i1, speed_i2, speed_fl, speed_st,
   compound, tyre_life_laps, is_personal_best)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
"""


def main() -> None:
    conn = psycopg2.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT session_key FROM incidents WHERE session_key IS NOT NULL ORDER BY session_key")
    all_keys = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT DISTINCT session_key FROM lap_features WHERE session_key IS NOT NULL")
    done = {r[0] for r in cur.fetchall()}
    conn.close()

    todo = [k for k in all_keys if k not in done]
    print(f"telemetry backfill: {len(all_keys)} sessions, {len(done)} already done, {len(todo)} to go", flush=True)

    total_laps = ok = fail = 0
    for i, sk in enumerate(todo, 1):
        time.sleep(0.4)  # throttle to stay under FastF1's request rate limit
        try:
            meta = session_meta(sk)
            if not meta:
                print(f"[{i}/{len(todo)}] sk={sk} no OpenF1 meta — skip", flush=True)
                fail += 1
                continue
            s, laps = load_fastf1(meta)
            if s is None:
                print(f"[{i}/{len(todo)}] sk={sk} {meta.get('location')} {meta.get('session_name')} — no FastF1 laps ({type(laps).__name__ if laps else 'none'})", flush=True)
                fail += 1
                continue
            # s.t0_date is only set by the telemetry load, which this script
            # skips, so it raised every time and left t0 None on every session.
            # The car_data stream alone reaches the same value.
            t0 = t0_from_car_data(s)
            rows = lap_rows(sk, laps, t0, None)
            w = psycopg2.connect(DB)
            wc = w.cursor()
            execute_batch(wc, INSERT, rows, page_size=500)
            w.commit()
            w.close()
            total_laps += len(rows)
            ok += 1
            print(f"[{i}/{len(todo)}] sk={sk} {meta.get('year')} {meta.get('location')} {meta.get('session_name')} — {len(rows)} laps", flush=True)
        except Exception as exc:
            fail += 1
            print(f"[{i}/{len(todo)}] sk={sk} FAILED: {type(exc).__name__}: {exc}", flush=True)

    print(f"DONE — sessions ok={ok} fail={fail}, total laps inserted={total_laps}", flush=True)


if __name__ == "__main__":
    main()
