"""
parse_pdf — HIGH priority queue task.

Accepts a PDF file path or URL, extracts raw text with pdfplumber,
runs the decision parser, and writes the structured record to
data/parsed/decisions.jsonl (idempotent via sha256 dedup).

Enqueued by:
  - fia_scraper when a new PDF is downloaded
  - scripts/enrich_decisions.py for re-parsing existing PDFs
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from celery import shared_task

logger = logging.getLogger(__name__)

ROOT        = Path(__file__).resolve().parents[4]
PARSED_JSONL = ROOT / "data" / "parsed" / "decisions.jsonl"
HASH_DB      = ROOT / "data" / "ingested_hashes.json"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_hashes() -> set[str]:
    if HASH_DB.exists():
        return set(json.loads(HASH_DB.read_text()).keys())
    return set()


def _save_hash(sha256: str) -> None:
    db: dict = json.loads(HASH_DB.read_text()) if HASH_DB.exists() else {}
    db[sha256] = True
    HASH_DB.write_text(json.dumps(db))


@shared_task(
    name="packages.pipeline.workers.tasks.parse_pdf.parse_pdf_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="high",
)
def parse_pdf_task(self, pdf_path: str, pdf_url: str = "", season: int = 0) -> dict:
    """
    Parse a single PDF and append to decisions.jsonl.

    Args:
        pdf_path: Absolute path to the PDF on disk.
        pdf_url:  Original FIA URL (stored in the record).
        season:   Season year override (inferred from path if 0).

    Returns:
        dict with keys: doc_id, sha256_hash, status ('new'|'duplicate')
    """
    try:
        import pdfplumber
    except ImportError:
        raise RuntimeError("pdfplumber not installed — run: pip install pdfplumber")

    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    sha256 = _sha256(path)
    existing = _load_hashes()
    if sha256 in existing:
        logger.info("Duplicate PDF skipped: %s", path.name)
        return {"doc_id": sha256[:16], "sha256_hash": sha256, "status": "duplicate"}

    # Extract text
    try:
        with pdfplumber.open(path) as pdf:
            raw_text = "\n".join(
                (page.extract_text() or "") for page in pdf.pages
            ).strip()
    except Exception as exc:
        logger.warning("pdfplumber failed on %s: %s — will queue OCR fallback", path.name, exc)
        ocr_fallback_task.apply_async(args=[pdf_path, pdf_url, season], queue="bulk")
        return {"doc_id": sha256[:16], "sha256_hash": sha256, "status": "queued_ocr"}

    needs_ocr = len(raw_text) < 100

    # Infer season from path if not given
    if not season:
        for part in path.parts:
            if part.isdigit() and 2015 <= int(part) <= 2030:
                season = int(part)
                break

    doc_id = sha256[:16]
    record = {
        "doc_id":         doc_id,
        "sha256_hash":    sha256,
        "title":          path.stem.replace("_", " "),
        "pdf_url":        pdf_url or str(path),
        "season":         season,
        "raw_text":       raw_text,
        "char_count":     len(raw_text),
        "needs_ocr":      needs_ocr,
        "parser_version": "v1.0-celery",
    }

    # Enqueue structured extraction
    extract_text_task.apply_async(args=[record], queue="default")

    # Append to JSONL
    PARSED_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with PARSED_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    _save_hash(sha256)
    logger.info("Parsed: %s (%d chars)", path.name, len(raw_text))
    return {"doc_id": doc_id, "sha256_hash": sha256, "status": "new"}


# Import here to avoid circular import — tasks reference each other
from packages.pipeline.workers.tasks.extract_text import extract_text_task  # noqa: E402
from packages.pipeline.workers.tasks.ocr_fallback import ocr_fallback_task  # noqa: E402
