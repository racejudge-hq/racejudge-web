"""
Backfill incidents table from decisions.jsonl.

Reads all parsed decisions, runs the 3-layer IncidentExtractor on each,
and inserts the results into the incidents table.

Idempotent: skips decisions that already have an incident row.

Usage:
    # All seasons
    python scripts/backfill_incidents.py

    # Specific season only
    python scripts/backfill_incidents.py --season 2024

    # Dry run (print stats, no DB writes)
    python scripts/backfill_incidents.py --dry-run

    # Force re-extraction even if incident exists
    python scripts/backfill_incidents.py --force
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s %(message)s")
log = logging.getLogger(__name__)

PARSED_JSONL = ROOT / "data" / "parsed" / "decisions.jsonl"
RAW_PDF_DIR = ROOT / "data" / "raw_pdfs"


def _local_pdf(rec: dict) -> Path | None:
    """Locate the source PDF for a decision, for the extractor's OCR fallback.

    The extractor only reaches layers 2 and 3 when it is handed a path, and this
    script never passed one — so a scanned decision had no way to recover, it
    just landed with empty fields.

    Only text-poor documents get a path. The extractor also escalates when layer
    1 finds fewer than two fields, but that condition does not mean the text
    failed to parse: it fires on the 85 administrative documents in the corpus
    ("RNCs used per driver up to now" and friends), which carry ~1,400 clean
    characters and simply have no incident to report. Re-reading those through
    OCR cannot invent fields that were never written, so handing them a path
    only buys a slow no-op. No decision currently in the corpus has a thin text
    layer, so this returns None throughout today's data — it is here for the
    scanned document that eventually turns up.
    """
    if not rec.get("needs_ocr") and (rec.get("char_count") or 0) >= 100:
        return None
    key = rec.get("r2_key") or ""
    if not key:
        return None
    path = RAW_PDF_DIR / key.replace("pdfs/", "", 1)
    return path if path.exists() else None


def _load_decisions(season: int | None) -> list[dict]:
    if not PARSED_JSONL.exists():
        log.error("No decisions found at %s", PARSED_JSONL)
        sys.exit(1)
    records = []
    with PARSED_JSONL.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if season is None or r.get("season") == season:
                records.append(r)
    log.info("Loaded %d decisions%s", len(records),
             f" for season {season}" if season else "")
    return records


async def _get_existing_doc_ids() -> set[str]:
    """Return set of doc_ids that already have incident rows."""
    try:
        from sqlalchemy import select

        from packages.db.database import _get_session_factory
        from packages.db.models import Incident

        factory = _get_session_factory()
        if factory is None:
            return set()
        async with factory() as db:
            result = await db.execute(select(Incident.doc_id).distinct())
            return {row[0] for row in result.all()}
    except Exception as exc:
        log.warning("Could not fetch existing incidents: %s", exc)
        return set()


async def _insert_incident(db, result) -> str | None:
    """Insert one ExtractionResult into incidents table. Returns incident_id."""
    try:
        from packages.db.models import Incident
        inc = Incident(
            doc_id              = result.doc_id,
            drivers             = result.drivers,
            involved_drivers    = result.involved_drivers,
            lap                 = result.lap_number,
            # extractor may yield an int turn number; column is Text and
            # asyncpg does not coerce int → varchar
            corner              = str(result.corner) if result.corner is not None else None,
            article_cited       = result.article_cited or [],
            infraction_category = result.infraction_category,
            penalty_type        = result.penalty_type,
            penalty_seconds     = result.penalty_seconds,
            penalty_points      = result.penalty_points or 0,
            penalty_suspended   = result.penalty_suspended,
            contact             = result.contact,
            reasoning_text      = result.reasoning_text or "",
            extractor_version   = result.extractor_version,
        )
        db.add(inc)
        await db.flush()
        return inc.incident_id
    except Exception as exc:
        await db.rollback()
        log.warning("Insert failed for doc_id=%s: %s", result.doc_id, exc)
        return None


async def run_backfill(season: int | None, dry_run: bool, force: bool) -> None:
    from packages.pipeline.extractors.incident_extractor import IncidentExtractor

    records = _load_decisions(season)
    existing: set[str] = set()
    if not force and not dry_run:
        existing = await _get_existing_doc_ids()
        log.info("Already extracted: %d decisions", len(existing))

    extractor = IncidentExtractor(enable_layoutlm=False)

    stats = {"total": 0, "inserted": 0, "skipped": 0, "failed": 0}

    if dry_run:
        for rec in records:
            result = extractor.extract(rec, _local_pdf(rec))
            stats["total"] += 1
            if result.penalty_type:
                stats["inserted"] += 1
            else:
                stats["failed"] += 1
        log.info("[DRY RUN] Would process %d records", stats["total"])
        log.info("  Penalty extracted: %d", stats["inserted"])
        log.info("  Low confidence:    %d", stats["failed"])
        return

    try:
        from packages.db.database import _get_session_factory
        factory = _get_session_factory()
        if factory is None:
            log.error("DATABASE_URL not set — cannot write to Postgres")
            sys.exit(1)
    except ImportError:
        log.error("SQLAlchemy not installed — pip install sqlalchemy[asyncio] asyncpg")
        sys.exit(1)

    async with factory() as db:
        for i, rec in enumerate(records, 1):
            doc_id = rec.get("doc_id", "unknown")
            stats["total"] += 1

            if doc_id in existing:
                stats["skipped"] += 1
                continue

            result = extractor.extract(rec, _local_pdf(rec))
            inc_id = await _insert_incident(db, result)
            if inc_id:
                stats["inserted"] += 1
                if i % 100 == 0:
                    await db.commit()
                    log.info("Progress: %d/%d (inserted=%d, skipped=%d, failed=%d)",
                             i, len(records), stats["inserted"],
                             stats["skipped"], stats["failed"])
            else:
                stats["failed"] += 1

        await db.commit()

    log.info("Backfill complete.")
    log.info("  Total:    %d", stats["total"])
    log.info("  Inserted: %d", stats["inserted"])
    log.info("  Skipped:  %d", stats["skipped"])
    log.info("  Failed:   %d", stats["failed"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill incidents table from decisions.jsonl")
    parser.add_argument("--season",  type=int,  help="Only process this season")
    parser.add_argument("--dry-run", action="store_true", help="Print stats without writing")
    parser.add_argument("--force",   action="store_true", help="Re-extract even if row exists")
    args = parser.parse_args()

    asyncio.run(run_backfill(args.season, args.dry_run, args.force))


if __name__ == "__main__":
    main()
