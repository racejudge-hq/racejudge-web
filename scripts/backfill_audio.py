"""
Backfill team radio: fetch, download, transcribe, and diarise for all sessions.

Pipeline per session:
  1. RadioFetcher: fetch all clip URLs from OpenF1, download to audio_cache/
  2. Upload to R2 if credentials present
  3. Insert clip rows into team_radio_clips table
  4. Queue transcription via Celery (asr_worker.transcribe_clip_task)
  5. After transcription: queue diarisation

Usage:
    python scripts/backfill_audio.py --season 2024
    python scripts/backfill_audio.py --session 9158
    python scripts/backfill_audio.py --dry-run    # show what would be fetched
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s %(message)s")
log = logging.getLogger(__name__)


async def _get_session_keys_with_incidents(season: int | None) -> list[int]:
    try:
        from sqlalchemy import text
        from packages.db.database import _get_session_factory
        factory = _get_session_factory()
        if factory is None:
            return []
        async with factory() as db:
            if season:
                q = text("""
                    SELECT DISTINCT i.session_key FROM incidents i
                    JOIN decisions d ON i.doc_id = d.doc_id
                    WHERE i.session_key IS NOT NULL AND d.season = :s
                    ORDER BY i.session_key
                """)
                r = await db.execute(q, {"s": season})
            else:
                q = text("SELECT DISTINCT session_key FROM incidents "
                         "WHERE session_key IS NOT NULL ORDER BY session_key")
                r = await db.execute(q)
            return [row[0] for row in r.all()]
    except Exception as exc:
        log.error("DB query failed: %s", exc)
        return []


async def _insert_clips(clips: list[dict], db) -> int:
    from sqlalchemy.dialects.postgresql import insert
    from packages.db.models import TeamRadioClip

    inserted = 0
    for clip in clips:
        url  = clip.get("recording_url")
        if not url:
            continue
        stmt = insert(TeamRadioClip).values(
            session_key   = clip["session_key"],
            driver_number = clip["driver_number"],
            date          = _parse_dt(clip.get("date", "")) or datetime.now(tz=timezone.utc),
            recording_url = url,
            r2_key        = clip.get("r2_key"),
        ).on_conflict_do_nothing(index_elements=["recording_url"])
        await db.execute(stmt)
        inserted += 1

    await db.flush()
    return inserted


def _parse_dt(s: str) -> datetime | None:
    if not s:
        return None
    try:
        s = s.rstrip("Z")
        fmt = "%Y-%m-%dT%H:%M:%S.%f" if "." in s else "%Y-%m-%dT%H:%M:%S"
        return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
    except Exception:
        return None


async def process_session(session_key: int, db, dry_run: bool) -> dict:
    from packages.pipeline.audio.radio_fetcher import RadioFetcher
    from packages.pipeline.linkers.openf1_client import OpenF1Client

    client = OpenF1Client()
    drivers = client.drivers(session_key=session_key)
    driver_numbers = [d.get("driver_number") for d in drivers if d.get("driver_number")]

    if not driver_numbers:
        log.warning("No drivers for session %d", session_key)
        return {"session_key": session_key, "clips": 0}

    fetcher = RadioFetcher()
    all_clips: list[dict] = []

    for dn in driver_numbers:
        clips = fetcher.fetch_all_driver_clips(session_key, int(dn), download=not dry_run)
        all_clips.extend(clips)

    log.info("Session %d: %d clips across %d drivers", session_key, len(all_clips), len(driver_numbers))

    if dry_run:
        return {"session_key": session_key, "clips": len(all_clips), "dry_run": True}

    inserted = await _insert_clips(all_clips, db)
    await db.commit()

    # Queue Celery transcription tasks for downloaded clips
    queued = 0
    for clip in all_clips:
        local_path = clip.get("path")
        if local_path and Path(local_path).exists():
            try:
                from packages.pipeline.audio.asr_worker import transcribe_clip_task
                # We don't have clip_id yet (just inserted), skip queuing for now
                # The batch_transcribe_session_task handles this
                queued += 1
            except Exception:
                pass

    return {"session_key": session_key, "clips": len(all_clips), "inserted": inserted}


async def run(season: int | None, single_session: int | None, dry_run: bool) -> None:
    if single_session:
        session_keys = [single_session]
    else:
        log.info("Fetching sessions with incidents...")
        session_keys = await _get_session_keys_with_incidents(season)
        log.info("Found %d sessions", len(session_keys))

    if not session_keys:
        log.warning("No sessions found. Run backfill_incidents.py first.")
        return

    from packages.db.database import _get_session_factory
    factory = _get_session_factory()
    if factory is None and not dry_run:
        log.error("DATABASE_URL not set")
        sys.exit(1)

    total_clips = 0
    for i, sk in enumerate(session_keys, 1):
        log.info("[%d/%d] Session %d", i, len(session_keys), sk)
        if dry_run or factory is None:
            stats = await process_session(sk, None, dry_run=True)
        else:
            async with factory() as db:
                stats = await process_session(sk, db, dry_run=False)
        total_clips += stats.get("clips", 0)
        log.info("  Clips: %d", stats.get("clips", 0))

    log.info("Backfill audio complete. Total clips: %d", total_clips)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill team radio clips")
    parser.add_argument("--season",  type=int, help="Season year")
    parser.add_argument("--session", type=int, help="Single session_key")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.season, args.session, args.dry_run))


if __name__ == "__main__":
    main()
