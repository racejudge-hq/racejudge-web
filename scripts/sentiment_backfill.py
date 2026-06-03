"""
Sentiment backfill — Phase 5.

Reads all team_radio_clips that have a transcript but no sentiment_score,
runs packages.ml.sentiment.classify_radio() on each, and writes
sentiment_score + urgency_score back to the database.

Usage:
    cd /path/to/RaceJudge && source .venv/bin/activate
    python scripts/sentiment_backfill.py

    # Process only 1 session worth of clips (for testing):
    python scripts/sentiment_backfill.py --session-limit 1

    # Dry run (no DB writes):
    python scripts/sentiment_backfill.py --dry-run

Requires: DATABASE_URL in environment or .env file
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("sentiment_backfill")


def _load_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _get_db_conn():
    import psycopg2
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL not set. Add it to .env or export it.")
    return psycopg2.connect(db_url)


def run_backfill(session_limit: int | None = None, dry_run: bool = False) -> dict:
    from packages.ml.sentiment import classify_radio

    conn = _get_db_conn()
    cur  = conn.cursor()

    if session_limit:
        cur.execute(f"""
            SELECT rc.clip_id, rc.transcript
            FROM team_radio_clips rc
            JOIN (
                SELECT DISTINCT session_key
                FROM team_radio_clips
                WHERE transcript IS NOT NULL AND transcript != ''
                ORDER BY session_key DESC
                LIMIT {session_limit}
            ) s ON rc.session_key = s.session_key
            WHERE rc.transcript IS NOT NULL AND rc.transcript != ''
              AND rc.sentiment_score IS NULL
            ORDER BY rc.date DESC
        """)
    else:
        cur.execute("""
            SELECT clip_id, transcript
            FROM team_radio_clips
            WHERE transcript IS NOT NULL AND transcript != ''
              AND sentiment_score IS NULL
            ORDER BY date DESC
        """)

    clips = cur.fetchall()
    log.info("Found %d clips to score", len(clips))

    processed = 0
    errors = 0

    for clip_id, transcript in clips:
        try:
            result = classify_radio(transcript)
            sentiment_score = result.get("sentiment_score", 0.0)
            urgency_score   = result.get("urgency_score", 0.0)

            if not dry_run:
                cur.execute(
                    """
                    UPDATE team_radio_clips
                    SET sentiment_score = %s, urgency_score = %s
                    WHERE clip_id = %s
                    """,
                    (sentiment_score, urgency_score, clip_id),
                )
                if processed % 50 == 0:
                    conn.commit()

            processed += 1
            if processed % 100 == 0:
                log.info("Progress: %d/%d scored", processed, len(clips))

        except Exception as exc:
            log.error("Error scoring clip_id=%s: %s", clip_id, exc)
            errors += 1

    if not dry_run:
        conn.commit()

    cur.close()
    conn.close()

    log.info(
        "Done. processed=%d errors=%d dry_run=%s",
        processed, errors, dry_run,
    )
    return {"processed": processed, "skipped": len(clips) - processed - errors, "errors": errors}


def main() -> None:
    _load_env()

    parser = argparse.ArgumentParser(description="Sentiment backfill for team_radio_clips")
    parser.add_argument("--session-limit", type=int, default=None,
                        help="Process only N most-recent sessions")
    parser.add_argument("--dry-run", action="store_true",
                        help="Score but do not write to DB")
    args = parser.parse_args()

    result = run_backfill(session_limit=args.session_limit, dry_run=args.dry_run)
    print(f"Result: {result}")


if __name__ == "__main__":
    main()
