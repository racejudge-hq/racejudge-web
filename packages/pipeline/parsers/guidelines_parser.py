"""
FIA Penalty Guidelines parser — Phase 1 (DB seed).

Parses the FIA Penalty Guidelines PDF (2025 edition, ~100 infraction types)
and Driving Standards Guidelines into structured rows for the `guidelines` table.

Documents:
  - 2025 FIA Penalty Guidelines (14 May 2025)
  - Driving Standards Guidelines v4.1 (20 Feb 2025)

Output row fields (match guidelines table in schema.sql):
  - document_name      TEXT
  - section            TEXT
  - article_number     TEXT
  - article_text       TEXT
  - recommended_penalty TEXT
  - effective_date     DATE

Usage:
    from packages.pipeline.parsers.guidelines_parser import parse_guidelines_pdf
    rows = parse_guidelines_pdf("path/to/penalty_guidelines_2025.pdf")

Dependencies: pdfplumber (already in requirements.txt for Phase 1)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class GuidelineRow:
    document_name: str
    section: str | None
    article_number: str
    article_text: str
    recommended_penalty: str | None
    effective_date: str | None  # ISO date string e.g. "2025-05-14"
    source_page: int | None = None


# ---------------------------------------------------------------------------
# Regex patterns for FIA guidelines document structure
# ---------------------------------------------------------------------------

# Article numbers: "Art. 38.1", "38.1", "Article 38.1"
_ARTICLE_RE = re.compile(
    r"(?:Art(?:icle)?\.?\s*)?(\d{1,3}(?:\.\d{1,3}){0,2})\s*[–\-:]?\s*(.+)",
    re.IGNORECASE,
)

# Penalty recommendations embedded in text
_PENALTY_RE = re.compile(
    r"(?:penalty|sanction|decision)[:\s]+([^\n.;]{5,120})",
    re.IGNORECASE,
)

# Section headers (ALL CAPS lines or numbered section titles)
_SECTION_RE = re.compile(r"^([A-Z][A-Z\s\-/]{4,80})$")

# Effective date patterns
_DATE_RE = re.compile(
    r"(?:effective|dated?|as of)\s+(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4}|\d{4}[\/\-]\d{1,2}[\/\-]\d{1,2})",
    re.IGNORECASE,
)


def _normalize_date(raw: str) -> str | None:
    """Try to normalise a raw date string to YYYY-MM-DD."""
    raw = raw.strip()
    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            from datetime import datetime
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw


def _extract_effective_date(text: str) -> str | None:
    m = _DATE_RE.search(text)
    if m:
        return _normalize_date(m.group(1))
    return None


# ---------------------------------------------------------------------------
# PDF parser
# ---------------------------------------------------------------------------

def _require_pdfplumber():
    try:
        import pdfplumber
        return pdfplumber
    except ImportError:
        raise ImportError(
            "pdfplumber not installed. Run: pip install pdfplumber"
        )


def parse_guidelines_pdf(
    pdf_path: str | Path,
    document_name: str | None = None,
    effective_date: str | None = None,
) -> list[GuidelineRow]:
    """
    Parse a FIA guidelines PDF into structured GuidelineRow records.

    Heuristic parsing strategy:
    1. Extract text page by page with pdfplumber
    2. Detect section headers (ALL CAPS lines)
    3. Detect article number lines (e.g. "38.1 Causing a collision")
    4. Extract recommended penalty from surrounding text
    5. Return one GuidelineRow per article
    """
    pdfplumber = _require_pdfplumber()
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    doc_name = document_name or pdf_path.stem
    rows: list[GuidelineRow] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        # Try to detect effective_date from first 2 pages if not provided
        if effective_date is None:
            for page in pdf.pages[:2]:
                text = page.extract_text() or ""
                effective_date = _extract_effective_date(text)
                if effective_date:
                    break

        current_section: str | None = None
        current_article: str | None = None
        current_text_lines: list[str] = []

        def _flush_article(page_num: int | None = None):
            nonlocal current_article, current_text_lines
            if current_article and current_text_lines:
                combined = " ".join(current_text_lines).strip()
                penalty_m = _PENALTY_RE.search(combined)
                recommended = penalty_m.group(1).strip() if penalty_m else None
                rows.append(GuidelineRow(
                    document_name=doc_name,
                    section=current_section,
                    article_number=current_article,
                    article_text=combined,
                    recommended_penalty=recommended,
                    effective_date=effective_date,
                    source_page=page_num,
                ))
            current_article = None
            current_text_lines = []

        for page in pdf.pages:
            raw = page.extract_text() or ""
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue

                # Section header detection
                if _SECTION_RE.match(line) and len(line) > 5:
                    _flush_article(page.page_number)
                    current_section = line.title()
                    continue

                # Article number detection
                m = _ARTICLE_RE.match(line)
                if m:
                    _flush_article(page.page_number)
                    current_article = m.group(1)
                    rest = m.group(2).strip()
                    if rest:
                        current_text_lines = [rest]
                    continue

                # Continuation of current article
                if current_article:
                    current_text_lines.append(line)

        _flush_article()

    log.info("Parsed %d guideline rows from %s", len(rows), pdf_path.name)
    return rows


# ---------------------------------------------------------------------------
# Structured guideline data (hardcoded seed — fallback if no PDF available)
# ---------------------------------------------------------------------------

# Key FIA Penalty Guidelines entries (2025 edition, partial)
# Source: FIA Penalty Guidelines 14 May 2025
KNOWN_GUIDELINES: list[dict[str, Any]] = [
    {
        "document_name": "FIA Penalty Guidelines 2025",
        "section": "Driving Conduct",
        "article_number": "38.1",
        "article_text": "Causing a collision",
        "recommended_penalty": "5–10 second time penalty or drive-through",
        "effective_date": "2025-05-14",
    },
    {
        "document_name": "FIA Penalty Guidelines 2025",
        "section": "Driving Conduct",
        "article_number": "38.2",
        "article_text": "Causing a collision resulting in retirement of another driver",
        "recommended_penalty": "10–30 second time penalty or drive-through, 2–3 penalty points",
        "effective_date": "2025-05-14",
    },
    {
        "document_name": "FIA Penalty Guidelines 2025",
        "section": "Track Limits",
        "article_number": "33.3",
        "article_text": "Leaving the track and gaining a lasting advantage",
        "recommended_penalty": "5 second time penalty or reprimand",
        "effective_date": "2025-05-14",
    },
    {
        "document_name": "FIA Penalty Guidelines 2025",
        "section": "Pit Lane",
        "article_number": "34.7",
        "article_text": "Unsafe release from pit lane",
        "recommended_penalty": "5–10 second time penalty, 2 penalty points",
        "effective_date": "2025-05-14",
    },
    {
        "document_name": "FIA Penalty Guidelines 2025",
        "section": "Pit Lane",
        "article_number": "34.12",
        "article_text": "Pit lane speed limit exceeded",
        "recommended_penalty": "Fine (€200 per km/h over limit)",
        "effective_date": "2025-05-14",
    },
    {
        "document_name": "FIA Penalty Guidelines 2025",
        "section": "Blue Flags",
        "article_number": "20.5",
        "article_text": "Ignoring blue flags",
        "recommended_penalty": "5 second time penalty, 1 penalty point",
        "effective_date": "2025-05-14",
    },
    {
        "document_name": "FIA Penalty Guidelines 2025",
        "section": "Safety Car",
        "article_number": "55.13",
        "article_text": "Overtaking during safety car period",
        "recommended_penalty": "Drive-through or 30 second time penalty, 2–3 penalty points",
        "effective_date": "2025-05-14",
    },
    {
        "document_name": "FIA Penalty Guidelines 2025",
        "section": "Virtual Safety Car",
        "article_number": "55.14",
        "article_text": "Not respecting virtual safety car delta time",
        "recommended_penalty": "5–10 second time penalty, 1 penalty point",
        "effective_date": "2025-05-14",
    },
    {
        "document_name": "Driving Standards Guidelines v4.1",
        "section": "Defensive Driving",
        "article_number": "2.1",
        "article_text": "Defending position — one change of direction permitted",
        "recommended_penalty": "Reprimand to 5 second time penalty",
        "effective_date": "2025-02-20",
    },
    {
        "document_name": "Driving Standards Guidelines v4.1",
        "section": "Overtaking",
        "article_number": "3.1",
        "article_text": "Driver must be alongside before turn-in point to claim racing space",
        "recommended_penalty": "Reprimand to 5 second time penalty",
        "effective_date": "2025-02-20",
    },
]


def get_seed_guidelines() -> list[GuidelineRow]:
    """Return the hardcoded seed guidelines as GuidelineRow objects."""
    return [
        GuidelineRow(**{k: v for k, v in g.items()})
        for g in KNOWN_GUIDELINES
    ]


def guidelines_to_dicts(rows: list[GuidelineRow]) -> list[dict]:
    """Convert GuidelineRow list to plain dicts for DB insertion."""
    return [
        {
            "document_name": r.document_name,
            "section": r.section,
            "article_number": r.article_number,
            "article_text": r.article_text,
            "recommended_penalty": r.recommended_penalty,
            "effective_date": r.effective_date,
        }
        for r in rows
    ]
