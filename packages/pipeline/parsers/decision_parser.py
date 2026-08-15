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

# Car number: "Car 44", "Car No. 44", "Car Number 06", "Cars 6 8 11 44", "#44".
# The plural and the spelled-out "number" both occur in the corpus and were
# missed by the original singular/"no." form: the technical rulings write "the
# engine intake air pressure of car number 05 was checked", and the multi-driver
# summonses are titled "Summons - Drivers of Cars 10 18 23 55". Zero-padding is
# harmless — int("06") is 6. Only the first car is returned, as before; the
# multi-car case is handled downstream by the driver resolver.
_CAR_RE = re.compile(
    r"(?:cars?\s*(?:nos?\.?|numbers?)?\s*|#)(\d{1,2})\b",
    re.IGNORECASE,
)

# The decision's own header states who is being judged, as "Driver 33 - Max
# Verstappen", and that is the only unambiguous statement of the subject in the
# document. Everything else has to be inferred from word order, which goes wrong
# whenever the title names the other party instead — "Decision - Alleged
# impeding of Car 20" is a ruling *against* car 1, not car 20. So this is tried
# before _CAR_RE, and it settles both the number and the name at once.
_SUBJECT_RE = re.compile(
    r"Driver\s+(\d{1,2})\s*[-–]\s*"
    r"([A-Z][A-Za-zÀ-ÿ'’.\-]+(?:\s+[A-Z][A-Za-zÀ-ÿ'’.\-]+){1,3})",
)

# A summons issued to several drivers over one incident carries them all under
# the same header, the first on the "No / Driver" line and the rest on bare
# continuation lines:
#
#     No / Driver 6 – Nicholas Latifi
#     8 – Romain Grosjean
#     11 – Sergio Perez
#     44 – Lewis Hamilton
#
# _SUBJECT_RE sees only the first, so the other three were dropped entirely.
# The continuation form is deliberately anchored to the whole line and requires
# a capitalised name: a bare "number – text" pattern occurs all over the body
# (dates, article references, lap tables) and matches nothing here because the
# scan stops at the first line that is not a driver.
_SUBJECT_CONT_RE = re.compile(
    r"^[ \t]*(\d{1,2})[ \t]*[-–][ \t]*"
    r"([A-Z][A-Za-zÀ-ÿ'’.\-]+(?:\s+[A-Z][A-Za-zÀ-ÿ'’.\-]+){1,3})[ \t]*$",
)

# The Fact section is the stewards' own one-line statement of what happened, and
# it is the only place the *other* cars in an incident are named reliably. The
# title also often names them ("Decision - Car 31 - T2 incident with Cars 11 and
# 27") but the title cannot be trusted for this: some are duplicated from a
# neighbouring document, and a 2026 summons titled "Car 4" is really Norris, who
# now runs #1 — reading counterparties from the title invents a second driver
# out of the subject's own stale number. The section ends at the next heading;
# the PDF text layer glues that heading to the sentence ("InfringementAlleged
# breach of..."), which is why the terminators are not anchored to a line start.
_FACT_RE = re.compile(
    r"\bFacts?\b\s*(.*?)(?=\b(?:Infring[e]?ment|Infringment|Offence|Decision|Reason)\b)",
    re.IGNORECASE | re.DOTALL,
)

# "Cars 11, 27 and 31", "cars 14, 18, 4 & 44", "Cars 6 8 11 44". _CAR_RE stops
# at the first number, so a three-car collision recorded only the one car the
# regex happened to reach first.
_CAR_LIST_RE = re.compile(
    r"\bcars?\s*(?:nos?\.?|numbers?)?\s*"
    r"(\d{1,2}(?:\s*(?:,|and|&|/)\s*\d{1,2}|\s+\d{1,2})*)",
    re.IGNORECASE,
)
_NUM_RE = re.compile(r"\d{1,2}")

# The Decision section is the operative ruling — the sentence that says what the
# stewards actually ordered. Suspension is read from here and nowhere else,
# because the surrounding prose is full of the same word used to mean other
# things: a red-flagged "session, which was suspended", and a 2020 protest
# arguing at length about whether DAS is a "suspension system". Both sit in the
# Reason section and both would otherwise register as suspended penalties.
_DECISION_RE = re.compile(
    r"\bDecision\b\s*(.*?)(?=\bReason\b|\Z)",
    re.IGNORECASE | re.DOTALL,
)

# A penalty is suspended when it is imposed but not enforced unless the party
# reoffends. Two distinct shapes, and the difference is not cosmetic:
#
#   full     "Fine of €25,000 – Suspended."          → nothing was served
#   partial  "fined €50,000, €25,000 of which is
#             suspended for the remainder of 2025"   → half really was paid
#
# Recording both as a plain boolean would claim Leclerc's €50,000 fine went
# unserved when he in fact paid €25,000 of it.
#
# Every space here is \s+ on purpose: the PDF text layer breaks these sentences
# across lines mid-phrase ("€20,000 of\nwhich is suspended"), so a literal space
# silently reads a partial suspension as a total one.
_SUSPENDED_PARTIAL_RE = re.compile(
    r"(?:"
    # "€20,000 of which is suspended", "€350,000 of the fine is suspended".
    # The connector is mandatory — without it this also swallows the *full*
    # form "fined €5.000, suspended for 12 months", which has a single amount.
    r"[€$£][\d.,]+\s+(?:of\s+which|of\s+the\s+(?:fine|penalty))"
    r"(?:\s+(?:is|was|be|would\s+be))?\s+suspend"
    r"|of\s+which\s+[€$£]?[\d.,]+(?:\s+(?:is|was|be|would\s+be))?\s+suspend"
    r"|with\s+[€$£][\d.,]+\s+suspend"
    r"|suspended?\s+in\s+parts?"
    r"|partly\s+suspend"
    r")",
    re.IGNORECASE,
)
_SUSPENDED_RE = re.compile(r"\bsuspend(?:ed|s)?\b", re.IGNORECASE)

# Some rulings carry no "Decision" heading at all — the 2024 Austin track-invasion
# fine is laid out as numbered clauses under "Description". Those still have to be
# read, so the fallback scans the whole document but demands that the suspension
# sit next to the thing being suspended. That proximity is what keeps out the two
# unrelated senses of the word: a "suspension system" in the 2020 DAS protest, and
# a "session, which was suspended due to a red flag".
_SUSPENDED_PENALTY_NEAR_RE = re.compile(
    r"(?:\bfine\b|\bpenalty\b|[€$£][\d.,]+)[^.]{0,80}?\bsuspend",
    re.IGNORECASE,
)

# "The Super Licence of the driver of Car 20 is suspended for the next
# Competition" is a race ban — the suspension *is* the penalty, not a reprieve
# from one. It appears in the Decision section, so it has to be excluded by name.
_SUSPENDED_LICENCE_RE = re.compile(
    r"\b(?:super\s+)?licen[cs]e\b[^.]{0,80}?\bsuspend",
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
    # The second branch covers the Article 55.5 rulings ("Near collision behind
    # the safety car"), which state no overtake and so matched nothing at all.
    (re.compile(r"safety\s+car.*?(overtook?|pass(?:ed|ing))"
                r"|(?:incident|near\s+collision|collision)\s+behind\s+the\s+safety\s+car",
                re.IGNORECASE),                                            "safety car violation"),
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
    # Deliberately requires the deletion to be *stated*, not merely referred to.
    # A wider "lap time ... deleted" window was tried and reverted: it recovered
    # no additional documents and it mis-classified rulings whose Reason section
    # mentions a deletion in passing ("knew his lap time would be deleted") when
    # the actual Infringement was something else entirely.
    (re.compile(r"deleted\s+lap\s+time|lap\s+time[s]?\s+(?:was|were|are|is)\s+deleted"
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
    # "Practice Start Area" is a *place* in the pit lane, and it is named in the
    # Facts of rulings that are really pit-lane offences ("overtook several cars
    # in the Fast Lane whilst traversing the Working Lane to the Practice Start
    # Area"). Matching the bare noun phrase pulled six such rulings out of their
    # real category, so require the practice start to be the act itself —
    # performed, or the subject of the instruction that was breached.
    # The last two branches carry the rulings that *name* the offence, in the
    # title, which is the only place several of them state it. They are kept
    # narrow — "practice start infringement", or a title ending in "- Practice
    # Start" — because the pit-lane rulings above also discuss practice starts
    # in their Reason ("did perform a genuine practice start", "without doing a
    # practice start") and any looser branch takes them back.
    (re.compile(r"(?:perform|undert(?:ook|ake|aken)|complet|carr(?:y|ied)\s+out|execut)\w*"
                r"\s+(?:a\s+|the\s+)?practice\s+start"
                r"|practice\s+start(?:s)?\s+(?:outside|before|in\s+the\s+wrong)"
                r"|(?:considering|regarding|concerning)\s+practice\s+start"
                r"|practice\s+start\s+infringement"
                r"|-\s*(?:alleged\s+)?practice\s+start\s*$",
                re.IGNORECASE | re.MULTILINE),                             "practice start infringement"),
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

    # Off-track obligations (parades, fan events, briefings, the anthem).
    # The meeting/briefing branch deliberately requires offence language. Every
    # ruling that actually is one says "late for" / "late attendance" / "failed
    # to attend" / "behaviour in", whereas a bare mention of the drivers'
    # briefing turns up in the Reason narrative of wholly unrelated rulings —
    # the yellow-flag, escape-road and crossing-the-track decisions all cite it
    # — and a bare match captured those. Note the curly apostrophe: the PDFs
    # contain U+2019, and only the cleaned text is normalised to a straight one.
    (re.compile(r"drivers?['’]?\s*parade|fan\s+engagement"
                r"|(?:late\s+(?:for|attendance)|fail(?:ing|ed|ure)?\s+to\s+attend"
                r"|absence\s+from|behaviour\s+in)"
                r"[^.]{0,40}?drivers?['’]?\s*(?:meeting|briefing)"
                r"|late\s+attendance\s+of\s+(?:the\s+)?national\s+anthem",
                re.IGNORECASE),                                            "driver obligation breach"),

    # Deliberately last. "Breach of the Race Director's Event Notes" is the
    # catch-all article the FIA cites for offences that already have a specific
    # category above — pit lane infringements and practice starts among them —
    # so it must only win when nothing more specific matched. The curly
    # apostrophe (U+2019) is what the PDFs actually contain; a straight-quote
    # pattern missed every one of these.
    (re.compile(r"fail(?:ing|ed|ure)?\s+to\s+follow\s+(?:the\s+)?"
                r"(?:race\s+director|rd)['’]?s?\s+(?:instruction|event\s+note)",
                re.IGNORECASE),                                            "failure to follow Race Director instructions"),
]


# ---------------------------------------------------------------------------
# Extraction functions
# ---------------------------------------------------------------------------

def _first_match(pattern: re.Pattern, text: str, group: int = 1) -> str | None:
    m = pattern.search(text)
    return m.group(group) if m else None


def extract_car_number(text: str) -> int | None:
    m = _SUBJECT_RE.search(text)
    if m:
        return int(m.group(1))
    m = _CAR_RE.search(text)
    return int(m.group(1)) if m else None


def extract_driver_name(text: str) -> str | None:
    m = _SUBJECT_RE.search(text)
    if m:
        # Collapse the newline the PDF puts before the next header field.
        return " ".join(m.group(2).split("\n")[0].split())
    return _first_match(_DRIVER_RE, text)


def extract_subjects(text: str) -> list[tuple[int, str]]:
    """Every driver the document is a ruling *against*, as (car number, name).

    Normally one. A summons over a single incident can name several, each on its
    own line under the header, and those extra drivers were previously lost.

    Returns an empty list when the document has no subject header at all — the
    caller falls back to extract_car_number()/extract_driver_name(), which read
    the title and body. Order is the order the document lists them in, so the
    first entry is always the one the single-subject extractors return.
    """
    m = _SUBJECT_RE.search(text)
    if not m:
        return []
    subjects = [(int(m.group(1)), " ".join(m.group(2).split("\n")[0].split()))]

    # Continue down the block. m.end() lands mid-line whenever the name is
    # followed by more text on the same line, so drop that remainder first.
    rest = text[m.end():].split("\n")[1:]
    for line in rest:
        cont = _SUBJECT_CONT_RE.match(line)
        if not cont:
            break
        number = int(cont.group(1))
        if number not in {n for n, _ in subjects}:
            subjects.append((number, " ".join(cont.group(2).split())))
    return subjects


def extract_involved_cars(text: str, exclude: set[int] | None = None) -> list[int]:
    """Car numbers named in the Fact section other than the ones being judged.

    These are the counterparties to the incident — the car that was impeded, hit
    or forced off. They are not accused of anything by this document, so they are
    kept apart from the subject list rather than merged into it: a driver's
    penalty record must not grow because someone else drove into them.

    Order follows the document. Returns an empty list when the document states
    no other car, which is the common case — most rulings involve one car only.
    """
    m = _FACT_RE.search(text)
    if not m:
        return []
    skip = exclude or set()
    others: list[int] = []
    for group in _CAR_LIST_RE.finditer(m.group(1)):
        for raw in _NUM_RE.findall(group.group(1)):
            number = int(raw)
            if number not in skip and number not in others:
                others.append(number)
    return others


def extract_suspension(text: str) -> str | None:
    """Whether the penalty was suspended, and if so how much of it.

    Returns "full" when the whole penalty was suspended, "partial" when only a
    stated portion was, and None when it was served in the ordinary way.

    This matters because a suspended penalty is indistinguishable from a served
    one once it is reduced to a penalty_type. Hulkenberg's 2026 Canadian GP
    stop-and-go was suspended in its entirety and never served, but was stored
    as a plain "SG" — identical to a driver who actually served one. For a
    precedent engine that difference is the whole point of the ruling.

    Read from the Decision section where there is one; see _DECISION_RE for why.
    """
    m = _DECISION_RE.search(text)
    scope = m.group(1) if m else ""

    if scope.strip():
        if not _SUSPENDED_RE.search(scope):
            return None
    else:
        # No Decision heading — fall back to the whole document, but only accept
        # a suspension stated next to a fine or penalty.
        if not _SUSPENDED_PENALTY_NEAR_RE.search(text):
            return None
        scope = text

    if _SUSPENDED_LICENCE_RE.search(scope):
        return None
    return "partial" if _SUSPENDED_PARTIAL_RE.search(scope) else "full"


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
