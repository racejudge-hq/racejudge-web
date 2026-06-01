"""
Tesseract OCR fallback — Phase 2, Layer 2.

Triggered when pdfplumber yields < 100 chars (scanned / image-only PDFs).
Uses pdf2image to render each page at 300 DPI, then Tesseract 5 for OCR.

Prerequisites:
    pip install pytesseract pdf2image pillow
    brew install tesseract poppler   # macOS
    apt-get install tesseract-ocr poppler-utils  # Ubuntu

Returns raw OCR text with page separators.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

# Tesseract language config: English + common F1 abbreviations in whitelist
_TESS_CONFIG = "--oem 3 --psm 6"


def ocr_pdf(pdf_path: str | Path, dpi: int = 300) -> str:
    """
    Run Tesseract OCR on a PDF file.

    Args:
        pdf_path: Path to the PDF file.
        dpi:      Render resolution. 300 DPI is standard for FIA docs.

    Returns:
        Full OCR text, pages separated by form-feed character.

    Raises:
        RuntimeError: if pdf2image or pytesseract are not installed.
    """
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError as e:
        raise RuntimeError(
            f"OCR dependency missing: {e}\n"
            "Install: pip install pdf2image pytesseract pillow\n"
            "System: brew install tesseract poppler  (macOS)"
        ) from e

    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    log.info("OCR: rendering %s at %d DPI", path.name, dpi)
    pages = convert_from_path(str(path), dpi=dpi)

    page_texts: list[str] = []
    for i, page in enumerate(pages, 1):
        text = pytesseract.image_to_string(page, lang="eng", config=_TESS_CONFIG)
        page_texts.append(text)
        log.debug("  Page %d: %d chars", i, len(text))

    full_text = "\f".join(page_texts)
    log.info("OCR done: %s — %d chars over %d pages", path.name, len(full_text), len(pages))
    return full_text


def ocr_should_run(text: str, min_chars: int = 100) -> bool:
    """Return True if text is too short to have been properly extracted."""
    return len(text.strip()) < min_chars


def ocr_pdf_if_needed(pdf_path: str | Path, existing_text: str = "") -> tuple[str, bool]:
    """
    Run OCR only if existing_text is too short.

    Returns:
        (text, ran_ocr): text is the best available text; ran_ocr=True if OCR was used.
    """
    if not ocr_should_run(existing_text):
        return existing_text, False
    try:
        text = ocr_pdf(pdf_path)
        return text, True
    except Exception as exc:
        log.error("OCR failed for %s: %s", pdf_path, exc)
        return existing_text, False
