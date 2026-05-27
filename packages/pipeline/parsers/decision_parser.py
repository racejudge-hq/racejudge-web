"""
Structured extraction from FIA decision text — Phase 2.

Extracts:
  - car_number        (e.g. 44)
  - driver_name       (e.g. "Lewis Hamilton")
  - infraction_type   (e.g. "causing a collision", "track limits")
  - outcome           (e.g. "5 second time penalty", "reprimand", "no further action")
  - penalty_points    (e.g. 2)
  - lap_number        (e.g. 12)
  - session_type      (e.g. "race", "qualifying", "sprint")

Phase 2 milestone: >90% F1-score on field extraction.
Current approach: regex patterns on raw_text.
Phase 2 upgrade: LayoutLMv3 fine-tuned on labelled PDF tables.

Usage:
    from packages.pipeline.parsers.decision_parser import extract_incident
    fields = extract_incident(record)
"""

from __future__ import annotations

import re
from typing import Any


# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

# Car number: "Car 44", "Car No. 44", "#44"
_CAR_RE = re.compile(
    r"(?:car\s*(?:no\.?\s*)?|#)(\d{1,2})\b",
    re.IGNORECASE,
)

# Driver names — common F1 name endings after "driver" keyword
_DRIVER_RE = re.compile(
    r"(?:driver|competitor)\s+([A-Z][a-z]+(?: [A-Z][a-z]+)+)",
)

# Session type
_SESSION_RE = re.compile(
    r"\b(race|qualifying|sprint|practice|formation lap|reconnaissance)\b",
    re.IGNORECASE,
)

# Lap number
_LAP_RE = re.compile(
    r"\b(?:lap|turn)\s+(\d{1,3})\b",
    re.IGNORECASE,
)

# Penalty points — "2 penalty points"
_PEN_POINTS_RE = re.compile(
    r"(\d)\s+penalty\s+points?",
    re.IGNORECASE,
)

# Outcome detection: ordered by specificity
_OUTCOME_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"disqualif", re.IGNORECASE),               "disqualification"),
    (re.compile(r"drive[- ]through", re.IGNORECASE),        "drive-through penalty"),
    (re.compile(r"pit\s*lane\s*(?:through|drive)", re.IGNORECASE), "pit lane penalty"),
    (re.compile(r"(\d+)\s*second[s]?\s*time\s*penalty", re.IGNORECASE), "{n}s time penalty"),
    (re.compile(r"(\d+)\s*second[s]?\s*penalty", re.IGNORECASE),        "{n}s time penalty"),
    (re.compile(r"grid\s+(?:position\s+)?penalty", re.IGNORECASE),      "grid penalty"),
    (re.compile(r"reprimand", re.IGNORECASE),               "reprimand"),
    (re.compile(r"no\s+further\s+action", re.IGNORECASE),  "no further action"),
    (re.compile(r"warning", re.IGNORECASE),                 "warning"),
    (re.compile(r"fine\s+of\s+([\d,]+)\s*(?:euro|€|\$)", re.IGNORECASE), "fine"),
]

# Infraction type — ordered by specificity
_INFRACTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"caus(?:ing|ed)\s+a\s+collision", re.IGNORECASE),         "causing a collision"),
    (re.compile(r"track\s+limits?", re.IGNORECASE),                         "track limits"),
    (re.compile(r"unsafe\s+(?:release|act)", re.IGNORECASE),                "unsafe release"),
    (re.compile(r"pit\s*lane\s*speed(?:ing)?", re.IGNORECASE),              "pit lane speeding"),
    (re.compile(r"ignoring?\s+blue\s+flag", re.IGNORECASE),                 "ignoring blue flags"),
    (re.compile(r"(?:impeding|obstruct)", re.IGNORECASE),                   "impeding"),
    (re.compile(r"false\s+start", re.IGNORECASE),                           "false start"),
    (re.compile(r"start(?:ing)?\s+procedure", re.IGNORECASE),              "starting procedure"),
    (re.compile(r"weav(?:ing|e)", re.IGNORECASE),                          "weaving"),
    (re.compile(r"safety\s+car.*?(overtook?|pass(?:ed|ing))", re.IGNORECASE), "safety car violation"),
    (re.compile(r"virtual\s+safety\s+car", re.IGNORECASE),                 "VSC infringement"),
    (re.compile(r"yellow\s+flag", re.IGNORECASE),                          "yellow flag violation"),
    (re.compile(r"driving\s+(?:unnecessarily\s+)?slowly", re.IGNORECASE),  "driving unnecessarily slowly"),
    (re.compile(r"leaving\s+the\s+track", re.IGNORECASE),                  "leaving the track"),
    (re.compile(r"(?:media|pr)\s+commitment", re.IGNORECASE),              "media commitment breach"),
]


# ---------------------------------------------------------------------------
# Extraction functions
# ---------------------------------------------------------------------------

def _first_match(pattern: re.Pattern, text: str, group: int = 1) -> str | None:
    m = pattern.search(text)
    return m.group(group) if m else None


def extract_car_number(text: str) -> int | None:
    m = _CAR_RE.search(text)
    return int(m.group(1)) if m else None


def extract_driver_name(text: str) -> str | None:
    return _first_match(_DRIVER_RE, text)


def extract_session_type(text: str) -> str | None:
    m = _SESSION_RE.search(text)
    return m.group(1).lower() if m else None


def extract_lap_number(text: str) -> int | None:
    m = _LAP_RE.search(text)
    return int(m.group(1)) if m else None


def extract_penalty_points(text: str) -> int | None:
    m = _PEN_POINTS_RE.search(text)
    return int(m.group(1)) if m else None


def extract_outcome(text: str) -> str | None:
    for pattern, label in _OUTCOME_PATTERNS:
        m = pattern.search(text)
        if m:
            if "{n}" in label:
                # Extract the number
                try:
                    n = m.group(1)
                    return label.replace("{n}", n)
                except IndexError:
                    return label.replace("{n}s ", "")
            return label
    return None


def extract_infraction_type(text: str) -> str | None:
    # First try the title — it's usually more reliable than free text
    for pattern, label in _INFRACTION_PATTERNS:
        if pattern.search(text):
            return label
    return None


def extract_incident(record: dict) -> dict[str, Any]:
    """
    Extract structured fields from a parsed decision record.
    Returns a dict with extracted fields; values are None if not found.
    """
    title   = record.get("title", "")
    text    = record.get("raw_text", "")
    combined = f"{title}\n{text}"

    return {
        "doc_id":         record.get("doc_id"),
        "car_number":     extract_car_number(combined),
        "driver_name":    extract_driver_name(text),
        "infraction_type": extract_infraction_type(combined),
        "outcome":        extract_outcome(combined),
        "penalty_points": extract_penalty_points(combined),
        "lap_number":     extract_lap_number(text),
        "session_type":   extract_session_type(combined),
    }


def batch_extract(records: list[dict]) -> list[dict]:
    """Extract structured fields from a list of parsed decision records."""
    return [extract_incident(r) for r in records]
