"""
Seed drivers and teams reference tables from Jolpica-F1 API.

Jolpica-F1 is an open-source Ergast API mirror:
  https://api.jolpi.ca/ergast/f1/

No API key required. Rate-limited to 200 req/hour.

Usage:
    python scripts/seed_drivers.py               # all seasons 2019–2025
    python scripts/seed_drivers.py --season 2025 # single season
    python scripts/seed_drivers.py --cache-only  # update local JSON only, skip DB
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s %(message)s")
log = logging.getLogger(__name__)

CACHE_DIR     = ROOT / "data" / "reference"
DRIVERS_CACHE = CACHE_DIR / "drivers.json"
TEAMS_CACHE   = CACHE_DIR / "teams.json"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

JOLPICA_BASE = "https://api.jolpi.ca/ergast/f1"
REQUEST_DELAY = 1.0  # seconds between requests


def _fetch(url: str) -> dict:
    log.debug("GET %s", url)
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read())


def _fetch_drivers(season: int) -> list[dict]:
    url = f"{JOLPICA_BASE}/{season}/drivers.json?limit=30"
    try:
        data = _fetch(url)
        return data.get("MRData", {}).get("DriverTable", {}).get("Drivers", [])
    except Exception as exc:
        log.warning("Failed to fetch drivers for %d: %s", season, exc)
        return []


def _fetch_constructors(season: int) -> list[dict]:
    url = f"{JOLPICA_BASE}/{season}/constructors.json?limit=20"
    try:
        data = _fetch(url)
        return data.get("MRData", {}).get("ConstructorTable", {}).get("Constructors", [])
    except Exception as exc:
        log.warning("Failed to fetch constructors for %d: %s", season, exc)
        return []


def _jolpica_driver_to_record(d: dict, season: int) -> dict:
    return {
        "code":        d.get("code", ""),
        "full_name":   f"{d.get('givenName', '')} {d.get('familyName', '')}".strip(),
        "abbreviation": d.get("code", ""),
        "nationality": d.get("nationality", ""),
        "number":      int(d["permanentNumber"]) if d.get("permanentNumber") else None,
        "jolpica_id":  d.get("driverId"),
        "seasons":     [season],
        "active":      season >= 2024,
    }


def _jolpica_team_to_record(c: dict, season: int) -> dict:
    return {
        "name":       c.get("name", ""),
        "short_name": c.get("constructorId", ""),
        "jolpica_id": c.get("constructorId"),
        "active":     season >= 2024,
    }


def _merge_drivers(existing: list[dict], new_records: list[dict]) -> list[dict]:
    by_code: dict[str, dict] = {r["code"]: r for r in existing if r.get("code")}
    for r in new_records:
        code = r.get("code")
        if not code:
            continue
        if code in by_code:
            # Merge seasons list
            existing_seasons = set(by_code[code].get("seasons", []))
            existing_seasons.update(r.get("seasons", []))
            by_code[code]["seasons"] = sorted(existing_seasons)
        else:
            by_code[code] = r
    return list(by_code.values())


def _merge_teams(existing: list[dict], new_records: list[dict]) -> list[dict]:
    by_id: dict[str, dict] = {r["jolpica_id"]: r for r in existing if r.get("jolpica_id")}
    for r in new_records:
        jid = r.get("jolpica_id")
        if jid and jid not in by_id:
            by_id[jid] = r
    return list(by_id.values())


async def _upsert_drivers_db(drivers: list[dict]) -> None:
    try:
        from sqlalchemy.dialects.postgresql import insert

        from packages.db.database import _get_session_factory
        from packages.db.models import Driver

        factory = _get_session_factory()
        if factory is None:
            return

        async with factory() as db:
            for d in drivers:
                if not d.get("code"):
                    continue
                stmt = insert(Driver).values(
                    code         = d["code"],
                    full_name    = d.get("full_name", ""),
                    abbreviation = d.get("abbreviation"),
                    nationality  = d.get("nationality"),
                    number       = d.get("number"),
                    jolpica_id   = None,  # string ID from Jolpica, not integer
                    active       = d.get("active", False),
                ).on_conflict_do_update(
                    index_elements=["code"],
                    set_={
                        "full_name":    d.get("full_name", ""),
                        "active":       d.get("active", False),
                        "number":       d.get("number"),
                        "nationality":  d.get("nationality"),
                    }
                )
                await db.execute(stmt)
            await db.commit()
        log.info("Upserted %d drivers to DB", len(drivers))
    except Exception as exc:
        log.error("DB upsert failed: %s", exc)


async def _upsert_teams_db(teams: list[dict]) -> None:
    try:
        from sqlalchemy.dialects.postgresql import insert

        from packages.db.database import _get_session_factory
        from packages.db.models import Team

        factory = _get_session_factory()
        if factory is None:
            return

        async with factory() as db:
            for t in teams:
                if not t.get("name"):
                    continue
                stmt = insert(Team).values(
                    name       = t["name"],
                    short_name = t.get("short_name"),
                    active     = t.get("active", False),
                ).on_conflict_do_nothing()
                await db.execute(stmt)
            await db.commit()
        log.info("Upserted %d teams to DB", len(teams))
    except Exception as exc:
        log.error("DB upsert failed: %s", exc)


async def run(seasons: list[int], cache_only: bool) -> None:
    # Load existing cache
    existing_drivers: list[dict] = []
    existing_teams:   list[dict] = []
    if DRIVERS_CACHE.exists():
        existing_drivers = json.loads(DRIVERS_CACHE.read_text(encoding="utf-8"))
    if TEAMS_CACHE.exists():
        existing_teams = json.loads(TEAMS_CACHE.read_text(encoding="utf-8"))

    all_driver_records: list[dict] = []
    all_team_records:   list[dict] = []

    for season in seasons:
        log.info("Fetching season %d...", season)
        raw_drivers = _fetch_drivers(season)
        raw_teams   = _fetch_constructors(season)

        season_drivers = [_jolpica_driver_to_record(d, season) for d in raw_drivers]
        season_teams   = [_jolpica_team_to_record(c, season) for c in raw_teams]

        all_driver_records.extend(season_drivers)
        all_team_records.extend(season_teams)
        log.info("  Season %d: %d drivers, %d teams", season,
                 len(season_drivers), len(season_teams))
        time.sleep(REQUEST_DELAY)

    # Merge and save cache
    merged_drivers = _merge_drivers(existing_drivers, all_driver_records)
    merged_teams   = _merge_teams(existing_teams, all_team_records)

    DRIVERS_CACHE.write_text(json.dumps(merged_drivers, indent=2, ensure_ascii=False))
    TEAMS_CACHE.write_text(json.dumps(merged_teams, indent=2, ensure_ascii=False))
    log.info("Cache updated: %d drivers, %d teams", len(merged_drivers), len(merged_teams))

    # Invalidate in-memory driver resolver index
    try:
        import packages.pipeline.resolvers.driver_resolver as mod
        mod._indices = None
    except Exception:
        pass

    if cache_only:
        log.info("Cache-only mode — skipping DB write")
        return

    await _upsert_drivers_db(merged_drivers)
    await _upsert_teams_db(merged_teams)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed drivers/teams from Jolpica-F1")
    parser.add_argument("--season",     type=int, help="Single season to fetch")
    parser.add_argument("--cache-only", action="store_true", help="Write JSON only, skip DB")
    args = parser.parse_args()

    seasons = [args.season] if args.season else list(range(2019, 2026))
    asyncio.run(run(seasons, args.cache_only))


if __name__ == "__main__":
    main()
