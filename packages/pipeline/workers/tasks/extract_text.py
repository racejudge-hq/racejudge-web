"""
extract_text — DEFAULT priority queue task.

Takes a raw parsed record dict and runs the structured decision parser
(decision_parser.py + text_cleaner.py) to extract:
  - car_number, driver_name, infraction_type, outcome, penalty_points
  - lap_number, session_type, published_at

The enriched record is written back to decisions.jsonl (in-place update)
and optionally inserted into Postgres if DATABASE_URL is set.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from celery import shared_task

logger = logging.getLogger(__name__)

ROOT         = Path(__file__).resolve().parents[4]
PARSED_JSONL = ROOT / "data" / "parsed" / "decisions.jsonl"


def _update_jsonl(updated: dict) -> None:
    """Replace the record in decisions.jsonl matching doc_id."""
    if not PARSED_JSONL.exists():
        return
    lines = PARSED_JSONL.read_text(encoding="utf-8").splitlines()
    new_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if rec.get("doc_id") == updated["doc_id"]:
            new_lines.append(json.dumps(updated, ensure_ascii=False))
        else:
            new_lines.append(line)
    PARSED_JSONL.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


@shared_task(
    name="packages.pipeline.workers.tasks.extract_text.extract_text_task",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    queue="default",
)
def extract_text_task(self, record: dict) -> dict:
    """
    Run structured extraction on a parsed decision record.

    Args:
        record: Dict with at minimum doc_id, raw_text, title, season.

    Returns:
        Enriched record dict with extracted fields.
    """
    try:
        from packages.pipeline.parsers.decision_parser import (
            extract_car_number,
            extract_driver_name,
            extract_infraction_type,
            extract_lap_number,
            extract_outcome,
            extract_penalty_points,
            extract_session_type,
        )
        from packages.pipeline.parsers.text_cleaner import (
            clean_decision_text,
            extract_article_citations,
            normalize_decision_title,
        )
    except ImportError as exc:
        raise self.retry(exc=exc, countdown=60) from exc

    raw_text = record.get("raw_text", "")
    title    = record.get("title", "")

    cleaned_text  = clean_decision_text(raw_text)
    cleaned_title = normalize_decision_title(title)

    enriched = {
        **record,
        "title":           cleaned_title,
        "raw_text":        cleaned_text,
        "char_count":      len(cleaned_text),
        "car_number":      extract_car_number(cleaned_text),
        "driver_name":     extract_driver_name(cleaned_text),
        "infraction_type": extract_infraction_type(cleaned_text),
        "outcome":         extract_outcome(cleaned_text),
        "penalty_points":  extract_penalty_points(cleaned_text),
        "lap_number":      extract_lap_number(cleaned_text),
        "session_type":    extract_session_type(cleaned_text),
        "article_cited":   extract_article_citations(cleaned_text),
        "parser_version":  "v1.1-celery-enriched",
    }

    _update_jsonl(enriched)

    # Insert into Postgres if DATABASE_URL is set
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        _upsert_postgres(enriched, database_url)

    logger.info("Extracted: %s — %s / %s",
                enriched["doc_id"],
                enriched.get("infraction_type", "?"),
                enriched.get("outcome", "?"))
    return enriched


def _upsert_postgres(record: dict, database_url: str) -> None:
    try:
        import psycopg2
    except ImportError:
        logger.warning("psycopg2 not installed — skipping DB upsert")
        return

    cols_to_update = [
        "car_number", "driver_name", "infraction_type", "outcome",
        "penalty_points", "lap_number", "session_type", "parser_version",
    ]
    set_clause = ", ".join(f"{c} = %({c})s" for c in cols_to_update)

    try:
        conn = psycopg2.connect(database_url)
        cur  = conn.cursor()
        cur.execute(
            f"""
            UPDATE decisions SET {set_clause}
            WHERE doc_id = %(doc_id)s
            """,
            record,
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as exc:
        logger.error("Postgres upsert failed for %s: %s", record.get("doc_id"), exc)
