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

# The Reason section is the stewards' actual argument: what they weighed, what
# they accepted in mitigation, and why the penalty is the one they chose. It is
# the only part of a decision worth searching for precedent, so it is what the
# embeddings are built from.
_REASON_RE = re.compile(r"\bReason\b\s*(.*)\Z", re.IGNORECASE | re.DOTALL)

# Every decision closes with the same two paragraphs about the right of appeal
# and the independence of the stewards, followed by the signature block. None
# of it is reasoning, and leaving it in makes every document look alike to a
# similarity search.
_TAIL_BOILERPLATE_RE = re.compile(
    r"\n\s*(?:Competitors\s+are\s+reminded"
    r"|Decisions?\s+of\s+the\s+Stewards\s+are\s+taken\s+independently"
    r"|The\s+Stewards\s*$)",
    re.IGNORECASE | re.MULTILINE,
)

# bge-m3 accepts 8192 tokens, so this is nowhere near the model's limit; it is
# a guard against a malformed document, not a content decision. Cut at a
# sentence end so a truncated reason never stops mid-word.
_MAX_REASON_CHARS = 6000


def extract_reason(text: str) -> str:
    """Return the Reason section, stripped of the closing boilerplate.

    Falls back to the whole document when there is no Reason heading, which is
    the case for administrative sheets that carry no argument at all.

    The previous implementation searched for the first of several loose markers,
    one of which was "the stewards" — a phrase that appears in the *header* of
    every decision ("The Stewards, having received a report from the Race
    Director..."). It therefore started at the top of the document and kept a
    flat 2,000 characters, so on 289 incidents the stored reasoning was the
    header, the facts and the ruling, cut off mid-word before the argument
    began. On the 2024 Mexican GP misconduct case that meant losing the
    mitigation and the €10,000 fine entirely.
    """
    m = _REASON_RE.search(text or "")
    body = m.group(1) if m else (text or "")

    cut = _TAIL_BOILERPLATE_RE.search(body)
    if cut:
        body = body[: cut.start()]
    body = body.strip()

    if len(body) <= _MAX_REASON_CHARS:
        return body
    head = body[:_MAX_REASON_CHARS]
    stop = max(head.rfind(". "), head.rfind(".\n"))
    return (head[: stop + 1] if stop > _MAX_REASON_CHARS // 2 else head).strip()

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

# ── Event header ────────────────────────────────────────────────────────────
# Every decision opens with the event it belongs to and the dates it ran:
#
#     2024 AUSTRIAN GRAND PRIX
#     28 - 30 June 2024
#
# This is the document's own statement of which race weekend it came from —
# the only reliable way to attach a ruling to an event, since the filename
# carries only the season.
_EVENT_NAME_RE = re.compile(
    r"^[ \t]*(20\d\d)[ \t]+([A-Z][A-Z0-9'’À-Ž .\-]*?(?:GRAND[ \t]+PRIX|TESTING|TEST))[ \t]*$",
    re.MULTILINE,
)

# The 2020 70th Anniversary Grand Prix is printed with no year in front of it,
# being the only event of its name. The season then comes from the date line.
_EVENT_NAME_NO_YEAR_RE = re.compile(
    r"^[ \t]*([A-Z0-9][A-Z0-9'’À-Ž .\-]*?(?:GRAND[ \t]+PRIX|TESTING|TEST))[ \t]*$",
    re.MULTILINE,
)

# Some PDFs render the first letter of each word as a separate drop cap, which
# the text layer emits as two lines: "2024 U S G P" then "NITED TATES RAND RIX".
# Re-joining them letter to remainder recovers "UNITED STATES GRAND PRIX".
_DROPCAP_RE = re.compile(
    r"^[ \t]*(20\d\d)[ \t]+((?:[A-Z][ \t]+){1,5}[A-Z])[ \t]*\n[ \t]*([A-Z][A-Z'’À-Ž ]*)[ \t]*$",
    re.MULTILINE,
)

# "28 - 30 June 2024", "28 November - 1 December 2019", "6 – 9 August 2020".
# The month is stated once when the weekend does not cross a month boundary.
_EVENT_DATE_RE = re.compile(
    r"^[ \t]*(\d{1,2})(?:[ \t]+([A-Z][a-z]+))?[ \t]*[-–—][ \t]*"
    r"(\d{1,2})[ \t]+([A-Z][a-z]+)[ \t]+(20\d\d)[ \t]*$",
    re.MULTILINE,
)

_MONTHS = {
    m: i
    for i, m in enumerate(
        ["january", "february", "march", "april", "may", "june", "july",
         "august", "september", "october", "november", "december"],
        start=1,
    )
}

# Only the first part of a document can carry the header; searching further
# risks matching an event named in the body of a right-of-review decision.
_HEADER_WINDOW = 400


# Driver names — common F1 name endings after "driver" keyword
_DRIVER_RE = re.compile(
    r"(?:driver|competitor)\s+([A-Z][a-z]+(?: [A-Z][a-z]+)+)",
)

# Session type.
#
# The document states it outright, on its own line: "Session Race",
# "Session Sprint Qualifying". Read that line and nothing else. Scanning the
# whole document instead returns the first of these words to appear anywhere,
# and the standard preamble — "having received a report from the Race
# Director" — sits above the field on nearly every decision. Measured against
# the stated field across the corpus, the loose scan was wrong on 42.5% of the
# 1,144 documents that state one: every practice, qualifying and sprint
# document it could reach was being recorded as a race.
_SESSION_FIELD_RE = re.compile(
    r"^[ \t]*Session[ \t:]*(\S[^\n]{0,50})$",
    re.IGNORECASE | re.MULTILINE,
)

# Fallback for the ~460 documents with no Session field — protests, rights of
# review, 107% requests, and the administrative sheets. Officials and offices
# named after a session are not sessions, so they come out first.
_NOT_A_SESSION_RE = re.compile(
    r"\brace\s+(?:director|control|steward|number|engineer|officials?)\b",
    re.IGNORECASE,
)
# The match keeps whatever number trails the session name — the fallback reads
# the first session mentioned, so it has to capture "Practice 1" whole rather
# than find "practice" and lose which one.
_SESSION_RE = re.compile(
    r"\b(sprint\s+(?:qualifying|shootout)|race|qualifying|sprint"
    r"|(?:free\s+)?practice\s*[123]?|fp\s*[123]?"
    r"|formation lap|reconnaissance)\b",
    re.IGNORECASE,
)

# Canonical session names, matching the vocabulary the sessions table accepts
# (see migration 0003) so a parsed session and a timing-feed session compare
# directly. Ordered: the longer name has to be tested before the shorter one it
# contains, or every sprint qualifying becomes a sprint.
_SESSION_CANON: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"shootout|sprint\W+qualif", re.IGNORECASE), "sprint_qualifying"),
    (re.compile(r"sprint", re.IGNORECASE),                   "sprint"),
    (re.compile(r"qualif", re.IGNORECASE),                   "qualifying"),
    (re.compile(r"practice\W*(?:session\W*)?1|\bfp\W*1", re.IGNORECASE), "practice_1"),
    (re.compile(r"practice\W*(?:session\W*)?2|\bfp\W*2", re.IGNORECASE), "practice_2"),
    (re.compile(r"practice\W*(?:session\W*)?3|\bfp\W*3", re.IGNORECASE), "practice_3"),
    (re.compile(r"practice", re.IGNORECASE),                 "practice"),
    (re.compile(r"race|grid procedure", re.IGNORECASE),      "race"),
    # Neither is a session in its own right, but both are where the incident
    # happened, so they are kept apart rather than folded into the race.
    (re.compile(r"reconnaissance", re.IGNORECASE),           "reconnaissance"),
    (re.compile(r"formation", re.IGNORECASE),                "formation lap"),
)

# Lap number — prefer "lap N" over "Turn N" (turn = corner, lap = race lap)
_LAP_RE = re.compile(r"\blap\s+(\d{1,3})\b", re.IGNORECASE)
_TURN_RE = re.compile(r"\bturn\s+(\d{1,3})\b", re.IGNORECASE)

# Penalty points — "2 penalty points"
_PEN_POINTS_RE = re.compile(
    r"(\d)\s+penalty\s+points?",
    re.IGNORECASE,
)

# ── Grid penalties ──────────────────────────────────────────────────────────
# A grid drop is the one penalty whose severity lives entirely in a number:
# a one-place drop and a ten-place drop are wholly different precedents, and
# "GRID" alone cannot tell them apart.
#
# The FIA writes the same ruling four ways, and spells the number out as often
# as it prints a digit:
#     "Drop of 5 grid positions for the next Race"
#     "a drop of three grid positions"
#     "5 grid place penalty for the Race"
#     "10 place grid penalty"
_GRID_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "fifteen": 15, "twenty": 20,
}
_GRID_NUM = r"(\d{1,2}|" + "|".join(_GRID_WORDS) + r")"
_GRID_POSITIONS_RE = re.compile(
    r"(?:"
    rf"drops?\s+of\s+{_GRID_NUM}\s+(?:grid\s+)?(?:position|place)"
    rf"|{_GRID_NUM}\s+(?:grid\s+)?(?:position|place)s?\s+(?:grid\s+)?(?:penalty|drop)"
    rf"|{_GRID_NUM}\s+grid\s+(?:position|place)s?"
    r")",
    re.IGNORECASE,
)

# Any wording that means "the grid penalty is the ruling", used for classifying
# the penalty type rather than reading its size.
_GRID_PENALTY_RE = re.compile(
    r"(?:"
    r"drops?\s+of\s+(?:\d{1,2}|" + "|".join(_GRID_WORDS) + r")\s+(?:grid\s+)?(?:position|place)"
    r"|grid\s+(?:position|place)\s+penalty"
    r"|(?:position|place)\s+grid\s+penalty"
    r"|grid\s+penalty"
    r")",
    re.IGNORECASE,
)

# Outcome detection: ordered by specificity
_OUTCOME_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"disqualif", re.IGNORECASE),               "disqualification"),
    # A pit lane start is the standard penalty for a parc fermé breach or a
    # power-unit change, and is a penalty in its own right — not a grid drop
    # and not a drive-through. 81 rulings impose one; before this pattern
    # existed 71 of them were stored with no penalty type at all.
    (re.compile(r"(?:required|permitted)\s+to\s+start\s+(?:the\s+\w+\s+)?"
                r"from\s+the\s+pit\s+lane"
                r"|start\s+the\s+race\s+from\s+the\s+pit\s+lane", re.IGNORECASE),
                                                            "pit lane start"),
    # Must precede the generic "N second ... penalty" rules: the FIA writes
    # "10 Second Stop-and-Go penalty", where the words between the number and
    # "penalty" made every stop-go ruling fall through to no outcome at all.
    (re.compile(r"stop[\s-]*(?:and)?[\s-]*go", re.IGNORECASE), "stop-and-go penalty"),
    (re.compile(r"drive[- ]through", re.IGNORECASE),        "drive-through penalty"),
    (re.compile(r"pit\s*lane\s*(?:through|drive)", re.IGNORECASE), "pit lane penalty"),
    (re.compile(r"(\d+)\s*second[s]?\s*time\s*penalty", re.IGNORECASE), "{n}s time penalty"),
    (re.compile(r"(\d+)\s*second[s]?\s*penalty", re.IGNORECASE),        "{n}s time penalty"),
    # "Drop of 5 grid positions" is how most grid penalties are actually
    # worded; matching only the literal phrase "grid penalty" left the majority
    # of them classified as nothing at all.
    (_GRID_PENALTY_RE,                                      "grid penalty"),
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


# Whether the cars actually touched. The Fact line says so in the stewards'
# own words; the infraction category — which is where this used to be inferred
# from — is a label applied afterwards and gets it wrong in both directions.
# Eight documents categorised "collision" describe impeding, an unsafe release
# or a car rejoining the track, and two describing a plain collision were
# stored as no contact.
_CONTACT_POS_RE = re.compile(
    r"collid|collision|made contact|contact (?:with|between)"
    r"|\bhit\b|rear[- ]end",
    re.IGNORECASE,
)
# "Near collision" and "near miss" are the opposite of contact, and say so
# using the same word.
_CONTACT_NEG_RE = re.compile(
    r"\bnear\s+(?:collision|miss)"
    r"|\b(?:no|without|not any)\s+(?:further\s+)?(?:contact|collision)"
    r"|did not (?:collide|make contact)",
    re.IGNORECASE,
)
# The FIA's deliberately neutral opener. It covers a collision and a near miss
# equally, so on its own it settles nothing.
_CONTACT_NEUTRAL_RE = re.compile(
    r"\bincident\s+(?:between|involving|with)\b",
    re.IGNORECASE,
)


def extract_contact(text: str) -> bool | None:
    """Whether the cars made contact, as stated in the Fact section.

    True when the stewards say they touched, False when the Fact describes an
    offence that involves no contact at all — track limits, speeding, impeding
    — and None when the document states no Fact, or states only that there was
    an "incident between" two cars, which is how the FIA writes both a crash
    and a near miss.
    """
    m = _FACT_RE.search(text or "")
    if not m:
        return None
    fact = m.group(1)
    if _CONTACT_NEG_RE.search(fact):
        return False
    if _CONTACT_POS_RE.search(fact):
        return True
    if _CONTACT_NEUTRAL_RE.search(fact):
        return None
    return False


# Some rulings name their drivers in a table rather than in the subject header:
# deleted lap times, safety car delta breaches, reconnaissance-lap offences.
#
#   No Turn Car Driver             Competitor                   Time of Day  Lap Time
#   1  4    24  Zhou Guanyu        Stake F1 Team Kick Sauber    12:56:34     1:29.677
#
# 152 documents are laid out this way, and every one of them was stored against
# nobody at all — a driver's record simply did not include the laps the
# stewards deleted from it.
_TABLE_HEADER_RE = re.compile(
    r"^[ \t]*(?:No\.?[ \t]+)?(?:Turn[ \t]+)?Car[ \t]+Driver\b",
    re.IGNORECASE | re.MULTILINE,
)
# Leading integers are the row number and, when the table has the column, the
# turn. The last one before the name is the car. The name run has to be matched
# lazily up to the time of day rather than as non-digits, because the team that
# follows it is full of them ("Stake F1 Team", "Visa Cash App RB F1 Team").
_TABLE_ROW_RE = re.compile(
    r"^[ \t]*\d{1,3}\.?[ \t]+(?:\d{1,3}[ \t]+)*(\d{1,3})[ \t]+"
    r"([A-Z].*?)[ \t]+\d{1,2}:\d{2}:\d{2}",
    re.MULTILINE,
)
# A second layout, used when one document imposes a penalty on several drivers
# at once. There is no time of day; the car and the driver are joined by a dash.
#
#   No  No / Driver           Competitor            Penalty
#   1   55 - Carlos Sainz     Scuderia Ferrari      10 second time penalty
_PENALTY_TABLE_HEADER_RE = re.compile(
    r"^[ \t]*No\.?[ \t]+No[ \t]*/[ \t]*Driver\b",
    re.IGNORECASE | re.MULTILINE,
)
_PENALTY_TABLE_ROW_RE = re.compile(
    r"^[ \t]*\d{1,3}\.?[ \t]+(\d{1,3})[ \t]*[-–—][ \t]*"
    r"([A-Z][A-Za-zÀ-ÿ'’.\-]+(?:[ \t]+[A-Za-zÀ-ÿ'’.\-]+){1,2})",
    re.MULTILINE,
)
# "Nyck de Vries", "Jean-Eric Vergne" — a lowercase particle belongs to the
# name, so the run does not stop at it.
_NAME_PARTICLES = {"de", "van", "von", "da", "del", "di", "la", "le"}


def extract_table_subjects(text: str) -> list[tuple[int, str]]:
    """Drivers named in a tabular ruling, as (car number, name).

    One entry per driver, in the order the table first names them — the table
    lists one row per deleted lap, so the same driver appears several times and
    is returned once.

    Returns an empty list unless the document actually has such a table: the
    header is required, because the row pattern on its own also matches a
    stray numbered list. Requiring it costs one document in the corpus and
    rules out every false positive. A table with a single row still counts —
    one car exceeding the safety car delta is still a ruling about that car.
    """
    text = text or ""
    seen: dict[int, str] = {}
    for header, row in ((_TABLE_HEADER_RE, _TABLE_ROW_RE),
                        (_PENALTY_TABLE_HEADER_RE, _PENALTY_TABLE_ROW_RE)):
        if not header.search(text):
            continue
        for match in row.finditer(text):
            number = int(match.group(1))
            if number in seen:
                continue
            seen[number] = _leading_name(match.group(2))
    return list(seen.items())


def _leading_name(cell: str) -> str:
    """The driver's name from a table cell that runs on into the team name.

    The columns collapse together in the text layer — "Zhou Guanyu Stake F1
    Team Kick Sauber" is one run — so the name is taken as the first two words,
    extended over a lowercase particle: "Nyck de Vries", "Jean-Eric Vergne".
    """
    words = cell.split()
    name = words[:1]
    for word in words[1:3]:
        name.append(word)
        if word.lower() not in _NAME_PARTICLES:
            break
    return " ".join(name)


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


def extract_event_header(text: str) -> dict[str, Any] | None:
    """The race weekend a decision belongs to, as the document states it.

    Returns {"season", "event_name", "start_date", "end_date"} or None. Dates
    are ISO strings and may be absent even when the name is found.

    Needed because a decision's season is all that reaches the database
    otherwise, which is far too coarse to attribute a ruling to the panel that
    issued it — a season has two dozen panels.
    """
    head = text[:_HEADER_WINDOW]
    dm = _EVENT_DATE_RE.search(head)

    name: str | None = None
    season: int | None = None
    m = _EVENT_NAME_RE.search(head)
    if m:
        season, name = int(m.group(1)), _collapse_spaces(m.group(2))
    else:
        d = _DROPCAP_RE.search(head)
        if d:
            season = int(d.group(1))
            caps, rest = d.group(2).split(), d.group(3).split()
            if len(caps) == len(rest):
                name = " ".join(c + r for c, r in zip(caps, rest, strict=True))
        elif dm:
            n = _EVENT_NAME_NO_YEAR_RE.search(head)
            if n:
                season, name = int(dm.group(5)), _collapse_spaces(n.group(1))
    if not name or season is None:
        return None

    out: dict[str, Any] = {
        "season": season,
        "event_name": name,
        "start_date": None,
        "end_date": None,
    }

    if dm:
        d1, m1, d2, m2, year = dm.groups()
        end_month = _MONTHS.get(m2.lower())
        # The start month is only printed when the weekend crosses one.
        start_month = _MONTHS.get((m1 or m2).lower())
        if start_month and end_month:
            y = int(year)
            # A weekend running December into January belongs to the earlier year.
            start_year = y - 1 if start_month > end_month else y
            out["start_date"] = f"{start_year:04d}-{start_month:02d}-{int(d1):02d}"
            out["end_date"] = f"{y:04d}-{end_month:02d}-{int(d2):02d}"

    return out


def _collapse_spaces(s: str) -> str:
    return " ".join(s.split())


# A decision prints Time twice. The first is in the letterhead, next to the
# document number and date, and is when the FIA published — often hours after
# the flag. The second sits in the incident block, directly above the Session
# field, and is when the incident happened. Take the last one before Session.
_TIME_FIELD_RE = re.compile(r"^[ \t]*Time[ \t:]+(\d{1,2}):(\d{2})", re.IGNORECASE | re.MULTILINE)


def extract_incident_time(text: str) -> tuple[int, int] | None:
    """Local circuit time of the incident, as (hour, minute).

    Local, not UTC — the FIA prints circuit time and never says so. Turning it
    into an instant needs the session's GMT offset, which is why this returns
    the clock reading rather than pretending to a timezone it does not know.

    Returns None when the document has no Session field to anchor on, or no
    Time above it: an "All Teams" notice carries only the publication time, and
    reading that as the incident time would put the incident after the race.
    """
    text = text or ""
    session = _SESSION_FIELD_RE.search(text)
    if not session:
        return None
    before = [m for m in _TIME_FIELD_RE.finditer(text) if m.start() < session.start()]
    if not before:
        return None
    hour, minute = int(before[-1].group(1)), int(before[-1].group(2))
    if hour > 23 or minute > 59:
        return None
    return hour, minute


def _canon_session(raw: str) -> str | None:
    for pattern, name in _SESSION_CANON:
        if pattern.search(raw):
            return name
    return None


def extract_session_type(text: str) -> str | None:
    """Which session the incident happened in, as the document states it.

    Returns one of the names the sessions table uses — race, qualifying,
    sprint, sprint_qualifying, practice_1..3 — or None when the document
    names no session at all, which is the honest answer for a protest or a
    right of review.
    """
    text = text or ""
    field = _SESSION_FIELD_RE.search(text)
    if field:
        return _canon_session(field.group(1))
    # No stated field: read the body, minus the offices named after sessions.
    m = _SESSION_RE.search(_NOT_A_SESSION_RE.sub(" ", text))
    return _canon_session(m.group(1)) if m else None


def extract_lap_number(text: str) -> int | None:
    m = _LAP_RE.search(text)
    return int(m.group(1)) if m else None


def extract_turn_number(text: str) -> int | None:
    m = _TURN_RE.search(text)
    return int(m.group(1)) if m else None


def extract_penalty_points(text: str) -> int | None:
    m = _PEN_POINTS_RE.search(text)
    return int(m.group(1)) if m else None


def extract_grid_positions(text: str) -> int | None:
    """How many places a grid penalty drops the driver.

    Read from the Decision section only. The Reason routinely names grid
    penalties that were *not* imposed — "the usual penalty for this is a 3 grid
    position penalty, however in mitigation…" — and reading the whole document
    would record the number the stewards declined to apply. "Starting grid
    position" in the narrative is a third, unrelated use of the same words.
    """
    m = _DECISION_RE.search(text)
    scope = m.group(1) if m and m.group(1).strip() else text

    g = _GRID_POSITIONS_RE.search(scope)
    if not g:
        return None
    raw = next(v for v in g.groups() if v)
    n = _GRID_WORDS.get(raw.lower()) if not raw.isdigit() else int(raw)
    # Article 28.3 accumulations reach 20; anything larger is a misread.
    return n if n is not None and 1 <= n <= 20 else None


def extract_outcome(text: str) -> str | None:
    """The penalty the stewards actually imposed.

    Read from the Decision section, because the Reason argues about penalties
    that were *not* imposed and used to win. Three examples from the corpus,
    all previously stored wrong: a parc fermé breach whose Decision reads
    "Required to start the Race from the pit lane" was recorded as a grid
    penalty, because its Reason explains the grid penalty it replaced; a
    failure-to-serve whose Decision reads "10 second time penalty" was recorded
    as a disqualification, that being the outcome the Reason weighed and
    rejected; and a weighing breach whose Decision reads "Warning." was
    likewise recorded as a disqualification. Scoping corrects 46 rulings.
    """
    m = _DECISION_RE.search(text)
    scope = m.group(1) if m and m.group(1).strip() else text

    for pattern, label in _OUTCOME_PATTERNS:
        m = pattern.search(scope)
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
