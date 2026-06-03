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
from dataclasses import dataclass
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
    except ImportError as exc:
        raise ImportError(
            "pdfplumber not installed. Run: pip install pdfplumber"
        ) from exc


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
    # -----------------------------------------------------------------------
    # FIA Penalty Guidelines 2025 — Driving Conduct
    # -----------------------------------------------------------------------
    {
        "document_name": "FIA Penalty Guidelines 2025",
        "section": "Driving Conduct",
        "article_number": "38.1",
        "article_text": (
            "Causing a collision — a driver must make every reasonable effort to avoid "
            "a collision with another competitor and must avoid causing avoidable accidents."
        ),
        "recommended_penalty": "5–10 second time penalty or drive-through",
        "effective_date": "2025-05-14",
    },
    {
        "document_name": "FIA Penalty Guidelines 2025",
        "section": "Driving Conduct",
        "article_number": "38.2",
        "article_text": (
            "Causing a collision resulting in the retirement of another driver or "
            "significant damage requiring that driver to pit for repairs."
        ),
        "recommended_penalty": "10–30 second time penalty or drive-through, 2–3 penalty points",
        "effective_date": "2025-05-14",
    },
    {
        "document_name": "FIA Penalty Guidelines 2025",
        "section": "Driving Conduct",
        "article_number": "38.3",
        "article_text": (
            "Reckless or negligent driving — driving in a manner that is deemed to be "
            "reckless or negligent and that could endanger another driver."
        ),
        "recommended_penalty": "10–30 second time penalty, 2–3 penalty points",
        "effective_date": "2025-05-14",
    },
    {
        "document_name": "FIA Penalty Guidelines 2025",
        "section": "Driving Conduct",
        "article_number": "38.4",
        "article_text": (
            "Forcing another driver off the track — a driver may not force another "
            "driver off the track and must leave at least one car width at the edge of "
            "the track."
        ),
        "recommended_penalty": "5–10 second time penalty, 1–2 penalty points",
        "effective_date": "2025-05-14",
    },
    {
        "document_name": "FIA Penalty Guidelines 2025",
        "section": "Driving Conduct",
        "article_number": "38.5",
        "article_text": (
            "Dangerous driving in the pit lane — driving in a manner deemed dangerous "
            "in the pit lane, including not maintaining a consistent line."
        ),
        "recommended_penalty": "Drive-through or 10 second time penalty, 2 penalty points",
        "effective_date": "2025-05-14",
    },
    # -----------------------------------------------------------------------
    # FIA Penalty Guidelines 2025 — Track Limits
    # -----------------------------------------------------------------------
    {
        "document_name": "FIA Penalty Guidelines 2025",
        "section": "Track Limits",
        "article_number": "33.3",
        "article_text": (
            "Leaving the track and gaining a lasting advantage — no driver may leave "
            "the track without a justifiable reason and must not gain a lasting advantage "
            "by doing so."
        ),
        "recommended_penalty": "5 second time penalty or reprimand",
        "effective_date": "2025-05-14",
    },
    {
        "document_name": "FIA Penalty Guidelines 2025",
        "section": "Track Limits",
        "article_number": "33.4",
        "article_text": (
            "Repeated track limit violations — persistent disregard of track limits "
            "at a single corner or multiple corners throughout the race."
        ),
        "recommended_penalty": "5–10 second time penalty, 1 penalty point",
        "effective_date": "2025-05-14",
    },
    # -----------------------------------------------------------------------
    # FIA Penalty Guidelines 2025 — Pit Lane
    # -----------------------------------------------------------------------
    {
        "document_name": "FIA Penalty Guidelines 2025",
        "section": "Pit Lane",
        "article_number": "34.7",
        "article_text": (
            "Unsafe release from pit lane — no car may be released from a garage or "
            "pit stop position in a way that could endanger team personnel or another "
            "driver."
        ),
        "recommended_penalty": "5–10 second time penalty, 2 penalty points",
        "effective_date": "2025-05-14",
    },
    {
        "document_name": "FIA Penalty Guidelines 2025",
        "section": "Pit Lane",
        "article_number": "34.12",
        "article_text": "Pit lane speed limit exceeded during a practice session, qualifying or race.",
        "recommended_penalty": "Fine (€200 per km/h over limit, minimum €500)",
        "effective_date": "2025-05-14",
    },
    {
        "document_name": "FIA Penalty Guidelines 2025",
        "section": "Pit Lane",
        "article_number": "34.13",
        "article_text": (
            "Lollipop released while wheel not fully attached or mechanic in dangerous "
            "position — car released before it is safe to do so."
        ),
        "recommended_penalty": "10 second time penalty, 2–3 penalty points",
        "effective_date": "2025-05-14",
    },
    # -----------------------------------------------------------------------
    # FIA Penalty Guidelines 2025 — Blue Flags
    # -----------------------------------------------------------------------
    {
        "document_name": "FIA Penalty Guidelines 2025",
        "section": "Blue Flags",
        "article_number": "20.5",
        "article_text": (
            "Ignoring blue flags — a lapped car must move aside for the leaders "
            "within three waved blue flags. Failure to do so is an infringement."
        ),
        "recommended_penalty": "5 second time penalty, 1 penalty point",
        "effective_date": "2025-05-14",
    },
    # -----------------------------------------------------------------------
    # FIA Penalty Guidelines 2025 — Safety Car
    # -----------------------------------------------------------------------
    {
        "document_name": "FIA Penalty Guidelines 2025",
        "section": "Safety Car",
        "article_number": "55.7",
        "article_text": (
            "Overtaking the safety car or another car before the safety car line — "
            "no car may pass the safety car until it returns to the pits."
        ),
        "recommended_penalty": "Drive-through or 30 second time penalty, 2–3 penalty points",
        "effective_date": "2025-05-14",
    },
    {
        "document_name": "FIA Penalty Guidelines 2025",
        "section": "Safety Car",
        "article_number": "55.13",
        "article_text": (
            "Overtaking another car during a safety car period — passing another "
            "competitor while the safety car is deployed and leading the field."
        ),
        "recommended_penalty": "Drive-through or 30 second time penalty, 2–3 penalty points",
        "effective_date": "2025-05-14",
    },
    {
        "document_name": "FIA Penalty Guidelines 2025",
        "section": "Safety Car",
        "article_number": "55.14",
        "article_text": (
            "Failure to keep a correct distance from the safety car — once in position "
            "behind the safety car, drivers must maintain a reasonable distance."
        ),
        "recommended_penalty": "5–10 second time penalty",
        "effective_date": "2025-05-14",
    },
    # -----------------------------------------------------------------------
    # FIA Penalty Guidelines 2025 — Virtual Safety Car
    # -----------------------------------------------------------------------
    {
        "document_name": "FIA Penalty Guidelines 2025",
        "section": "Virtual Safety Car",
        "article_number": "55.15",
        "article_text": (
            "Not respecting virtual safety car delta time — a driver must observe the "
            "VSC delta time displayed on the dashboard and may not exceed it."
        ),
        "recommended_penalty": "5–10 second time penalty, 1 penalty point",
        "effective_date": "2025-05-14",
    },
    # -----------------------------------------------------------------------
    # FIA Penalty Guidelines 2025 — Standing Start / Formation Lap
    # -----------------------------------------------------------------------
    {
        "document_name": "FIA Penalty Guidelines 2025",
        "section": "Start Procedure",
        "article_number": "36.5",
        "article_text": (
            "Jumping the start — a driver moves before the start signal in a way "
            "that provides a competitive advantage."
        ),
        "recommended_penalty": "Drive-through or 10 second time penalty",
        "effective_date": "2025-05-14",
    },
    {
        "document_name": "FIA Penalty Guidelines 2025",
        "section": "Start Procedure",
        "article_number": "36.12",
        "article_text": (
            "Stopped on formation lap — a driver unable to complete the formation lap "
            "must remain in position and be pushed to the pit lane."
        ),
        "recommended_penalty": "Drive-through or 10 second time penalty",
        "effective_date": "2025-05-14",
    },
    # -----------------------------------------------------------------------
    # FIA Penalty Guidelines 2025 — Flags
    # -----------------------------------------------------------------------
    {
        "document_name": "FIA Penalty Guidelines 2025",
        "section": "Flags and Signals",
        "article_number": "25.1",
        "article_text": (
            "Ignoring a yellow flag — drivers must slow down and be prepared to change "
            "direction when a yellow flag is displayed; overtaking is forbidden."
        ),
        "recommended_penalty": "5 second time penalty, 1 penalty point",
        "effective_date": "2025-05-14",
    },
    {
        "document_name": "FIA Penalty Guidelines 2025",
        "section": "Flags and Signals",
        "article_number": "25.4",
        "article_text": (
            "Ignoring a red flag — all cars must stop immediately and safely when a "
            "red flag is shown; a driver must not pass another car under red flags."
        ),
        "recommended_penalty": "10-place grid penalty or disqualification, 3 penalty points",
        "effective_date": "2025-05-14",
    },
    # -----------------------------------------------------------------------
    # FIA Penalty Guidelines 2025 — Weaving / Blocking
    # -----------------------------------------------------------------------
    {
        "document_name": "FIA Penalty Guidelines 2025",
        "section": "Driving Conduct",
        "article_number": "39.1",
        "article_text": (
            "Abnormal change of direction during braking — a driver may not make "
            "an abnormal change of direction when braking to prevent a following "
            "driver from attempting to pass."
        ),
        "recommended_penalty": "5–10 second time penalty, 1–2 penalty points",
        "effective_date": "2025-05-14",
    },
    {
        "document_name": "FIA Penalty Guidelines 2025",
        "section": "Driving Conduct",
        "article_number": "39.3",
        "article_text": (
            "Moving in the braking zone to defend position — moving under braking "
            "so that the following car must take evasive action."
        ),
        "recommended_penalty": "5–10 second time penalty, 1–2 penalty points",
        "effective_date": "2025-05-14",
    },
    # -----------------------------------------------------------------------
    # FIA Penalty Guidelines 2025 — Car / Technical
    # -----------------------------------------------------------------------
    {
        "document_name": "FIA Penalty Guidelines 2025",
        "section": "Technical",
        "article_number": "2.1",
        "article_text": (
            "Car not conforming to technical regulations — any part of the car not "
            "complying with the Technical Regulations at the time of scrutineering."
        ),
        "recommended_penalty": "Disqualification from session result",
        "effective_date": "2025-05-14",
    },
    {
        "document_name": "FIA Penalty Guidelines 2025",
        "section": "Technical",
        "article_number": "3.1",
        "article_text": (
            "Parc fermé infringement — car modified in a way not permitted while "
            "in parc fermé between qualifying and the race."
        ),
        "recommended_penalty": "Grid penalty (3–5 places) or start from pit lane",
        "effective_date": "2025-05-14",
    },
    # -----------------------------------------------------------------------
    # Driving Standards Guidelines v4.1 — Defensive Driving
    # -----------------------------------------------------------------------
    {
        "document_name": "Driving Standards Guidelines v4.1",
        "section": "Defensive Driving",
        "article_number": "2.1",
        "article_text": (
            "One change of direction to defend position — a driver may make one "
            "change of direction to defend their position; a second move to "
            "re-take the original line is permitted only if the first was to "
            "follow the corner."
        ),
        "recommended_penalty": "Reprimand to 5 second time penalty",
        "effective_date": "2025-02-20",
    },
    {
        "document_name": "Driving Standards Guidelines v4.1",
        "section": "Defensive Driving",
        "article_number": "2.2",
        "article_text": (
            "Crowding a car beyond the edge of the track — a driver may not force "
            "a car beyond the track edge even if that driver is in front and on "
            "the correct racing line."
        ),
        "recommended_penalty": "5 second time penalty, 1 penalty point",
        "effective_date": "2025-02-20",
    },
    # -----------------------------------------------------------------------
    # Driving Standards Guidelines v4.1 — Overtaking
    # -----------------------------------------------------------------------
    {
        "document_name": "Driving Standards Guidelines v4.1",
        "section": "Overtaking",
        "article_number": "3.1",
        "article_text": (
            "Claiming racing space — a driver may only claim racing space if they "
            "are sufficiently alongside the car ahead. The front wheel of the "
            "overtaking car must be at least level with the cockpit of the "
            "other car before the apex of the corner."
        ),
        "recommended_penalty": "Reprimand to 5 second time penalty",
        "effective_date": "2025-02-20",
    },
    {
        "document_name": "Driving Standards Guidelines v4.1",
        "section": "Overtaking",
        "article_number": "3.2",
        "article_text": (
            "Driver being overtaken must leave racing room — once the overtaking "
            "car is sufficiently alongside, the car being overtaken must leave "
            "at least one car width of space."
        ),
        "recommended_penalty": "Reprimand to 5 second time penalty, 1 penalty point",
        "effective_date": "2025-02-20",
    },
    {
        "document_name": "Driving Standards Guidelines v4.1",
        "section": "Overtaking",
        "article_number": "3.3",
        "article_text": (
            "Driver ahead braking unusually late — a driver defending position may "
            "not brake abnormally late in order to force the car behind to take "
            "evasive action."
        ),
        "recommended_penalty": "5 second time penalty, 1 penalty point",
        "effective_date": "2025-02-20",
    },
    # -----------------------------------------------------------------------
    # Driving Standards Guidelines v4.1 — Out-laps / Qualifying
    # -----------------------------------------------------------------------
    {
        "document_name": "Driving Standards Guidelines v4.1",
        "section": "Qualifying",
        "article_number": "5.1",
        "article_text": (
            "Unnecessarily impeding another car in qualifying — a driver must not "
            "unnecessarily impede another car, particularly when on a slow or "
            "preparation lap."
        ),
        "recommended_penalty": "Grid penalty (3–5 places)",
        "effective_date": "2025-02-20",
    },
    {
        "document_name": "Driving Standards Guidelines v4.1",
        "section": "Qualifying",
        "article_number": "5.2",
        "article_text": (
            "Driving unnecessarily slowly on an out-lap — creating an unsafe or "
            "dangerous situation by driving excessively slowly on an in-lap or "
            "out-lap in a way that endangers other drivers."
        ),
        "recommended_penalty": "Reprimand to 3-place grid penalty",
        "effective_date": "2025-02-20",
    },
    # -----------------------------------------------------------------------
    # International Sporting Code — Key Articles
    # -----------------------------------------------------------------------
    {
        "document_name": "FIA International Sporting Code 2025",
        "section": "Infringements and Penalties",
        "article_number": "12.1.1",
        "article_text": (
            "Any infringement of applicable regulations or supplementary regulations "
            "by a competitor or driver, whether or not explicitly described as an "
            "offence, may be penalised."
        ),
        "recommended_penalty": "Warning, fine, time penalty, or exclusion depending on severity",
        "effective_date": "2025-01-01",
    },
    {
        "document_name": "FIA International Sporting Code 2025",
        "section": "Infringements and Penalties",
        "article_number": "12.2.1",
        "article_text": (
            "Serious breach of statutory regulations — any serious breach of the "
            "statutory or supplementary regulations that could endanger safety or "
            "bring the sport into disrepute."
        ),
        "recommended_penalty": "Suspension or disqualification from the championship",
        "effective_date": "2025-01-01",
    },
    {
        "document_name": "FIA International Sporting Code 2025",
        "section": "Infringements and Penalties",
        "article_number": "12.4.1",
        "article_text": (
            "Penalty points — accumulated penalty points serve as a tally throughout "
            "a 12-month period. A driver reaching 12 points receives an automatic "
            "one-race ban."
        ),
        "recommended_penalty": "Race ban when 12 penalty points accumulated in 12 months",
        "effective_date": "2025-01-01",
    },
]


def get_seed_guidelines() -> list[GuidelineRow]:
    """Return the hardcoded seed guidelines as GuidelineRow objects."""
    return [
        GuidelineRow(**dict(g.items()))
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
