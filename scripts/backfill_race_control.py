"""
Backfill race_control_messages table from OpenF1 for all known sessions.

1. For each unique session_key found in incidents table, fetch RC messages from OpenF1.
2. Link RC messages to incidents using RaceControlLinker.
3. Attach weather context using WeatherLinker.

Usage:
    python scripts/backfill_race_control.py               # all sessions
    python scripts/backfill_race_control.py --season 2024 # one season
    python scripts/backfill_race_control.py --session 9158 # one session
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s %(message)s")
log = logging.getLogger(__name__)


async def _get_session_keys(season: int | None) -> list[int]:
    """Fetch distinct session_keys from incidents table (optionally filtered by season)."""
    try:
        from sqlalchemy import select, text
        from packages.db.database import _get_session_factory
        from packages.db.models import Incident, Decision

        factory = _get_session_factory()
        if factory is None:
            return []

        async with factory() as db:
            if season:
                stmt = text("""
                    SELECT DISTINCT i.session_key
                    FROM incidents i
                    JOIN decisions d ON i.doc_id = d.doc_id
                    WHERE i.session_key IS NOT NULL AND d.season = :season
                    ORDER BY i.session_key
                """)
                result = await db.execute(stmt, {"season": season})
            else:
                stmt = text("""
                    SELECT DISTINCT session_key FROM incidents
                    WHERE session_key IS NOT NULL ORDER BY session_key
                """)
                result = await db.execute(stmt)
            return [row[0] for row in result.all()]
    except Exception as exc:
        log.error("Failed to fetch session keys: %s", exc)
        return []


async def run(season: int | None, single_session: int | None) -> None:
    from packages.db.database import _get_session_factory
    from packages.pipeline.linkers.race_control_linker import RaceControlLinker
    from packages.pipeline.linkers.weather_linker import WeatherLinker

    factory = _get_session_factory()
    if factory is None:
        log.error("DATABASE_URL not set")
        sys.exit(1)

    if single_session:
        session_keys = [single_session]
    else:
        log.info("Fetching session keys from incidents table...")
        session_keys = await _get_session_keys(season)
        log.info("Found %d unique sessions", len(session_keys))

    if not session_keys:
        log.warning("No session keys found — run backfill_incidents.py first")
        return

    rc_linker      = RaceControlLinker()
    weather_linker = WeatherLinker()

    total_rc = 0
    total_linked = 0
    total_weather = 0

    for i, session_key in enumerate(session_keys, 1):
        log.info("[%d/%d] Processing session %d", i, len(session_keys), session_key)
        async with factory() as db:
            try:
                # Fetch + store + link RC messages
                stats = await rc_linker.link_session(session_key, db)
                total_rc     += stats["new_rc_messages"]
                total_linked += stats["rc_linked"]
                log.info(
                    "  RC: %d new messages, %d incidents linked",
                    stats["new_rc_messages"], stats["rc_linked"],
                )

                # Attach weather context
                wupdated = await weather_linker.backfill_session(session_key, db)
                total_weather += wupdated
                if wupdated:
                    log.info("  Weather: %d incidents updated", wupdated)
                await db.commit()
            except Exception as exc:
                log.error("  Session %d failed: %s", session_key, exc)
                await db.rollback()

    log.info("Backfill complete.")
    log.info("  RC messages inserted: %d", total_rc)
    log.info("  Incidents linked to RC: %d", total_linked)
    log.info("  Weather contexts added: %d", total_weather)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill race_control_messages from OpenF1")
    parser.add_argument("--season",  type=int, help="Filter by season year")
    parser.add_argument("--session", type=int, help="Process single session_key only")
    args = parser.parse_args()
    asyncio.run(run(args.season, args.session))


if __name__ == "__main__":
    main()
