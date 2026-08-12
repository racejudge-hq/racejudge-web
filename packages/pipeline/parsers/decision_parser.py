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

# Lap number — prefer "lap N" over "Turn N" (turn = corner, lap = race lap)
_LAP_RE = re.compile(r"\blap\s+(\d{1,3})\b", re.IGNORECASE)
_TURN_RE = re.compile(r"\bturn\s+(\d{1,3})\b", re.IGNORECASE)

# Penalty points — "2 penalty points"
_PEN_POINTS_RE = re.compile(
    r"(\d)\s+penalty\s+points?",
    re.IGNORECASE,
)

# Outcome detection: ordered by specificity
_OUTCOME_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"disqualif", re.IGNORECASE),               "disqualification"),
    # Must precede the generic "N second ... penalty" rules: the FIA writes
    # "10 Second Stop-and-Go penalty", where the words between the number and
    # "penalty" made every stop-go ruling fall through to no outcome at all.
    (re.compile(r"stop[\s-]*(?:and)?[\s-]*go", re.IGNORECASE), "stop-and-go penalty"),
    (re.compile(r"drive[- ]through", re.IGNORECASE),        "drive-through penalty"),
    (re.compile(r"pit\s*lane\s*(?:through|drive)", re.IGNORECASE), "pit lane penalty"),
    (re.compile(r"(\d+)\s*second[s]?\s*time\s*penalty", re.IGNORECASE), "{n}s time penalty"),
    (re.compile(r"(\d+)\s*second[s]?\s*penalty", re.IGNORECASE),        "{n}s time penalty"),
    (re.compile(r"grid\s+(?:position\s+)?penalty", re.IGNORECASE),      "grid penalty"),
    (re.compile(r"reprimand", re.IGNORECASE),               "reprimand"),
    (re.compile(r"no\s+further\s+action", re.IGNORECASE),  "no further action"),
    (re.compile(r"warning", re.IGNORECASE),                 "warning"),
    # The currency symbol precedes the amount in every FIA decision seen
    # ("is fined €5,000", "€1000", "€5.000"); the old pattern required it to
    # follow, so no fine was ever matched.
    (re.compile(r"fined?\s+(?:of\s+)?(?:€|EUR|\$|USD)?\s*([\d.,]+)", re.IGNORECASE), "fine"),
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

    # ---------------------------------------------------------------
    # Ruling types recovered by the v10 corpus scan.
    #
    # A full scan of all 1,249 unclassified incidents found 864 genuine
    # stewards' rulings that matched none of the patterns above. These cover
    # the ruling types that were being missed. They are APPENDED rather than
    # interleaved so that every document already classified by the patterns
    # above keeps its existing label — first match wins, so prior behaviour
    # is unchanged and this is purely additive.
    # ---------------------------------------------------------------

    # Track-limit enforcement: the stewards delete lap times rather than
    # issuing a penalty. 153 documents in the corpus.
    # ". {0,80}" rather than an adjacent verb: the FIA writes "the lap time
    # achieved on lap 12 is deleted", so the two halves are rarely adjacent.
    # Bounded and comma/period-free to keep it inside a single clause.
    (re.compile(r"deleted\s+lap\s+time|lap\s+time[s]?\b[^.]{0,80}?\bdelet"
                r"|did\s+not\s+use\s+the\s+track", re.IGNORECASE),         "deleted lap times"),
    (re.compile(r"forc(?:ing|ed)\s+(?:another\s+driver\s+)?off\s+the\s+track",
                re.IGNORECASE),                                            "forcing another driver off the track"),
    (re.compile(r"gain(?:ing|ed)\s+(?:a\s+)?(?:lasting\s+)?advantage", re.IGNORECASE),
                                                                           "gaining an advantage off track"),
    (re.compile(r"cross(?:ing|ed)\s+the\s+track", re.IGNORECASE),          "crossing the track"),

    # Parc fermé breaches — 85 documents.
    (re.compile(r"parc\s*ferm", re.IGNORECASE),                            "parc ferme breach"),

    # Safety-car-line time limit (SC2-SC1) — 66 documents.
    (re.compile(r"between\s+the\s+safety\s+car\s+lines|SC\s*2\s*-\s*SC\s*1",
                re.IGNORECASE),                                            "safety car line time limit"),
    (re.compile(r"fail(?:ing|ed|ure)?\s+to\s+maintain\s+(?:the\s+)?(?:required\s+)?"
                r"(?:\d+\s+car\s+lengths?|distance)", re.IGNORECASE),      "failing to maintain distance"),
    (re.compile(r"overtak(?:ing|en?)\s+under\s+(?:the\s+)?safety\s+car", re.IGNORECASE),
                                                                           "overtaking under safety car"),

    # Qualifying / sporting-regulation rulings.
    (re.compile(r"107\s*%|within\s+107", re.IGNORECASE),                   "107% rule"),
    (re.compile(r"fail(?:ing|ed|ure)?\s+to\s+follow\s+(?:the\s+)?"
                r"(?:race\s+director|rd)'?s?\s+instruction", re.IGNORECASE),
                                                                           "failure to follow Race Director instructions"),
    (re.compile(r"practice\s+start", re.IGNORECASE),                       "practice start infringement"),
    (re.compile(r"released\s+in\s+an\s+unsafe\s+condition", re.IGNORECASE), "released in an unsafe condition"),
    (re.compile(r"pit\s*(?:lane|exit)\s+infringement|infringement\s+at\s+pit\s+exit"
                r"|impeding\s+at\s+pit\s+exit", re.IGNORECASE),            "pit lane infringement"),

    # Technical / scrutineering.
    (re.compile(r"PU\s+element|power\s+unit\s+element|exceed(?:ed|ing)?\s+the\s+"
                r"permitted\s+number", re.IGNORECASE),                     "power unit element infringement"),
    (re.compile(r"technical\s+(?:infringement|non[- ]compliance)|scrutineer"
                r"|fuel\s+(?:sample|irregular)|tyre\s+pressure", re.IGNORECASE),
                                                                           "technical infringement"),
    # Deliberately not \bweight\b — "minimum weight" is a technical breach and
    # is caught by the pattern above; this is the weighbridge procedure only.
    (re.compile(r"weighing\s+(?:procedure|process)|weighbridge"
                r"|fail(?:ing|ed|ure)?\s+to\s+(?:stop\s+for\s+)?weigh", re.IGNORECASE),
                                                                           "weighing procedure"),

    # Off-track obligations (parades, fan events, briefings).
    (re.compile(r"drivers?'?\s*parade|fan\s+engagement|drivers?'?\s*(?:meeting|briefing)",
                re.IGNORECASE),                                            "driver obligation breach"),
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


def extract_turn_number(text: str) -> int | None:
    m = _TURN_RE.search(text)
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
