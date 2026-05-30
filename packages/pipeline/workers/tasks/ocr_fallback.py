"""
ocr_fallback — BULK priority queue task.

Used when pdfplumber extracts < 100 chars (scanned PDF or image-only).
Runs Tesseract OCR via pytesseract on each page rendered at 300 DPI.

Prerequisites:
  pip install pytesseract pdf2image pillow
  brew install tesseract          # macOS
  apt-get install tesseract-ocr   # Ubuntu/Debian

After OCR succeeds, the record is re-parsed by extract_text_task.
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

from celery import shared_task

logger = logging.getLogger(__name__)

ROOT         = Path(__file__).resolve().parents[4]
PARSED_JSONL = ROOT / "data" / "parsed" / "decisions.jsonl"


@shared_task(
    name="packages.pipeline.workers.tasks.ocr_fallback.ocr_fallback_task",
    bind=True,
    max_retries=1,
    default_retry_delay=120,
    queue="bulk",
    time_limit=300,     # 5 min max — OCR on a 20-page PDF is slow
    soft_time_limit=240,
)
def ocr_fallback_task(self, pdf_path: str, pdf_url: str = "", season: int = 0) -> dict:
    """
    OCR a PDF using Tesseract and enqueue for structured extraction.

    Args:
        pdf_path: Absolute path to the PDF on disk.
        pdf_url:  Original FIA URL.
        season:   Season year.

    Returns:
        dict with doc_id and char_count after OCR.
    """
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError:
        raise RuntimeError(
            "OCR dependencies not installed.\n"
            "Run: pip install pytesseract pdf2image pillow\n"
            "And: brew install tesseract  (macOS) or apt install tesseract-ocr"
        )

    path   = Path(pdf_path)
    logger.info("OCR fallback: %s", path.name)

    pages = convert_from_path(str(path), dpi=300)
    text_parts = []
    for i, page in enumerate(pages):
        page_text = pytesseract.image_to_string(page, lang="eng")
        text_parts.append(page_text)
        logger.debug("  Page %d: %d chars", i + 1, len(page_text))

    raw_text = "\n".join(text_parts).strip()
    logger.info("OCR done: %s — %d chars across %d pages",
                path.name, len(raw_text), len(pages))

    import hashlib
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    sha256_hex = sha256.hexdigest()
    doc_id     = sha256_hex[:16]

    if not season:
        for part in path.parts:
            if part.isdigit() and 2015 <= int(part) <= 2030:
                season = int(part)
                break

    record = {
        "doc_id":         doc_id,
        "sha256_hash":    sha256_hex,
        "title":          path.stem.replace("_", " "),
        "pdf_url":        pdf_url or str(path),
        "season":         season,
        "raw_text":       raw_text,
        "char_count":     len(raw_text),
        "needs_ocr":      False,      # OCR applied — no longer needed
        "parser_version": "v1.0-tesseract",
    }

    # Append/overwrite in JSONL
    PARSED_JSONL.parent.mkdir(parents=True, exist_ok=True)
    existing_ids: set[str] = set()
    lines: list[str] = []
    if PARSED_JSONL.exists():
        for line in PARSED_JSONL.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("doc_id") == doc_id:
                lines.append(json.dumps(record, ensure_ascii=False))
                existing_ids.add(doc_id)
            else:
                lines.append(line)
    if doc_id not in existing_ids:
        lines.append(json.dumps(record, ensure_ascii=False))
    PARSED_JSONL.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Enqueue structured extraction
    from packages.pipeline.workers.tasks.extract_text import extract_text_task
    extract_text_task.apply_async(args=[record], queue="default")

    return {"doc_id": doc_id, "char_count": len(raw_text), "status": "ocr_complete"}
