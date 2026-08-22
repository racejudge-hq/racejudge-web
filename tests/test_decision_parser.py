"""Tests for packages.pipeline.parsers.decision_parser."""

import pytest

from packages.pipeline.parsers.decision_parser import (
    batch_extract,
    extract_car_number,
    extract_contact,
    extract_driver_name,
    extract_event_header,
    extract_grid_positions,
    extract_incident,
    extract_incident_time,
    extract_infraction_type,
    extract_involved_cars,
    extract_lap_number,
    extract_outcome,
    extract_penalty_points,
    extract_reason,
    extract_session_type,
    extract_subjects,
    extract_suspension,
    extract_table_subjects,
    extract_video_refs,
)

# ---------------------------------------------------------------------------
# extract_car_number
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("Car 44 was involved", 44),
    ("Car No. 1 penalty", 1),
    ("#63 George Russell", 63),
    ("Car no.16 track limits", 16),
    ("no car number here", None),
    # Verbatim corpus phrasings the singular/"no." form used to miss.
    ("the engine intake air pressure of car number 05 was checked", 5),
    ("a completed scrutineering declaration form for car number 88", 88),
    ("Summons - Drivers of Cars 10 18 23 55", 10),
    ("Summons - Drivers of Cars 6 8 11 44", 6),
])
def test_extract_car_number(text, expected):
    assert extract_car_number(text) == expected


def test_subject_header_beats_a_title_naming_the_other_car():
    # Verbatim shape of a real ruling: the title names the driver who was
    # impeded, the header names the driver being judged. The header wins.
    text = ("Decision - Alleged impeding of Car 20\n"
            "Driver 1 - Max Verstappen\n"
            "Competitor Oracle Red Bull Racing\n"
            "Fact Impeded car 20 at turn 3.")
    assert extract_car_number(text) == 1
    assert extract_driver_name(text) == "Max Verstappen"


# ---------------------------------------------------------------------------
# extract_subjects — every driver the document rules against
# ---------------------------------------------------------------------------

# Verbatim from 2020 Italian GP document 24. Four drivers summoned over one
# incident; only the first was ever recorded.
_JOINT_SUMMONS = (
    "The drivers are required to report to the Stewards at 14:10 in relation to "
    "the incident below.\n"
    "No / Driver 6 – Nicholas Latifi\n"
    "8 – Romain Grosjean\n"
    "11 – Sergio Perez\n"
    "44 – Lewis Hamilton\n"
    "Reason Alleged driving unnecessarily slowly in turn 11 at 12:58 by cars 55, "
    "10, 23, 18, 11, 6, 8, alleged breach of Article 31.5\n"
)


def test_joint_summons_names_every_driver_it_is_issued_to():
    assert extract_subjects(_JOINT_SUMMONS) == [
        (6, "Nicholas Latifi"),
        (8, "Romain Grosjean"),
        (11, "Sergio Perez"),
        (44, "Lewis Hamilton"),
    ]
    # The single-subject extractors still return the first, unchanged.
    assert extract_car_number(_JOINT_SUMMONS) == 6
    assert extract_driver_name(_JOINT_SUMMONS) == "Nicholas Latifi"


def test_single_subject_document_yields_exactly_one_subject():
    text = ("No / Driver 31 - Esteban Ocon\n"
            "Competitor BWT Alpine F1 Team\n"
            "Time 20:52\n")
    assert extract_subjects(text) == [(31, "Esteban Ocon")]


def test_no_subject_header_yields_no_subjects():
    # The caller falls back to the title/body extractors; it must not get a
    # half-parsed subject here.
    assert extract_subjects("Decision - Car 23 - Failing to set a lap time") == []


# ---------------------------------------------------------------------------
# extract_involved_cars — the counterparties
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fact,subject,expected", [
    # Two- and three-car incidents, verbatim separators from the corpus.
    ("Fact Car 18 unnecessarily impeded Car 31 in turn 8. Infringement Breach", 18, [31]),
    ("Fact Turn 2 incident between Cars 11, 27 and 31 at 20:52. Infringement x", 31, [11, 27]),
    ("Fact Incident between cars 14, 18, 4 & 44 in Turn 1. Infringement x", 44, [14, 18, 4]),
    ("Fact Car 12 was released into the path of Car 22. Infringement x", 12, [22]),
    # One-car rulings must stay empty rather than inventing a counterparty.
    ("Fact Leaving the track without a justifiable reason. Infringement x", 10, []),
    ("Fact Car 10 exceeded the pit lane speed limit. Infringement x", 10, []),
])
def test_extract_involved_cars(fact, subject, expected):
    assert extract_involved_cars(fact, {subject}) == expected


def test_counterparties_come_from_the_fact_section_only():
    # The Reason discusses other cars at length; only the Fact states the
    # parties. Reading past the section boundary drags the whole narrative in.
    text = ("Fact Car 5 overtook Car 30 in a yellow flag zone.\n"
            "Infringement Breach of Appendix H.\n"
            "Decision 5 second time penalty.\n"
            "Reason The Stewards heard from the driver of Car 11 and the driver "
            "of Car 27 and reviewed video evidence of Cars 63 and 81.\n")
    assert extract_involved_cars(text, {5}) == [30]


def test_no_fact_section_yields_no_counterparties():
    assert extract_involved_cars("Summons - Car 4 - Alleged technical breach", {4}) == []


# ---------------------------------------------------------------------------
# extract_driver_name
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("driver Lewis Hamilton exceeded track limits", "Lewis Hamilton"),
    ("competitor George Russell caused a collision", "George Russell"),
    ("no driver name", None),
    ("driver Max Verstappen was penalised", "Max Verstappen"),
])
def test_extract_driver_name(text, expected):
    assert extract_driver_name(text) == expected


# ---------------------------------------------------------------------------
# extract_session_type
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("during the Race on lap 5", "race"),
    ("Qualifying session infringement", "qualifying"),
    ("Sprint race penalty", "sprint"),
    ("FP1 Practice incident", "practice_1"),
    ("Formation lap violation", "formation lap"),
    ("nothing relevant", None),
])
def test_extract_session_type(text, expected):
    assert extract_session_type(text) == expected


# The document states its session on a line of its own. Read that line — and
# only that line, because the preamble above it says "Race Director" on nearly
# every decision the FIA publishes. Reading the whole document instead was
# wrong on 42.5% of the 1,144 corpus documents that state a session: every
# practice, qualifying and sprint document became a race.
_SESSION_FIELD_DOC = """2025 SÃO PAULO GRAND PRIX
From The Stewards Document 23
The Stewards, having received a report from the Race Director, summoned
(document 15) and heard from the driver, have considered the following matter:
No / Driver 44 - Lewis Hamilton
Session {session}
Fact Failing to slow under double yellow flags
Decision Driver: Reprimand (Driving).
"""


@pytest.mark.parametrize("stated,expected", [
    ("Race",                "race"),
    ("Qualifying",          "qualifying"),
    ("Sprint",              "sprint"),
    ("Sprint Qualifying",   "sprint_qualifying"),
    ("Sprint Shootout",     "sprint_qualifying"),
    ("Practice 1",          "practice_1"),
    ("Free Practice 2",     "practice_2"),
    ("Practice 3",          "practice_3"),
    ("Reconnaissance Laps", "reconnaissance"),
    ("Pre-Race",            "race"),
])
def test_session_field_beats_the_race_director(stated, expected):
    doc = _SESSION_FIELD_DOC.format(session=stated)
    assert "Race Director" in doc          # the trap is present
    assert extract_session_type(doc) == expected


def test_sprint_qualifying_is_not_the_sprint():
    """'Sprint' is a prefix of 'Sprint Qualifying'. Order the tests wrong and
    every sprint-qualifying impeding case is filed under the sprint race."""
    assert extract_session_type("Session Sprint Qualifying") == "sprint_qualifying"
    assert extract_session_type("Session Sprint") == "sprint"


def test_no_stated_session_does_not_invent_one_from_the_preamble():
    """A protest or a right of review names no session. 'Race Director' is an
    official, not a session, and must not become one."""
    protest = (
        "2023 AUSTRALIAN GRAND PRIX\n"
        "From The Stewards Document 54\n"
        "Title Decision - Haas Protest\n"
        "The Stewards received a protest from the Race Director's report.\n"
    )
    assert extract_session_type(protest) is None


# ---------------------------------------------------------------------------
# extract_lap_number
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("on lap 12 of the race", 12),
    ("Turn 3 of lap 47", 47),
    ("no lap mentioned", None),
    ("lap 1 formation", 1),
])
def test_extract_lap_number(text, expected):
    assert extract_lap_number(text) == expected


# ---------------------------------------------------------------------------
# extract_penalty_points
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("2 penalty points added to licence", 2),
    ("3 penalty points", 3),
    ("no penalty points mentioned", None),
    ("1 penalty point on the licence", 1),
])
def test_extract_penalty_points(text, expected):
    assert extract_penalty_points(text) == expected


# ---------------------------------------------------------------------------
# extract_outcome
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("decision: 5 seconds time penalty", "5s time penalty"),
    ("10 second time penalty applied", "10s time penalty"),
    ("driver is disqualified from the race", "disqualification"),
    ("drive-through penalty is imposed", "drive-through penalty"),
    ("the stewards decided no further action", "no further action"),
    ("a reprimand is issued", "reprimand"),
    ("grid position penalty applied", "grid penalty"),
    ("received a warning from the stewards", "warning"),
    ("no outcome text here", None),
])
def test_extract_outcome(text, expected):
    assert extract_outcome(text) == expected


def test_extract_outcome_fine():
    result = extract_outcome("fined 10,000 euros for the infraction")
    assert result == "fine"


# ---------------------------------------------------------------------------
# extract_infraction_type
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("causing a collision with Car 44", "causing a collision"),
    ("track limits violation at Turn 9", "track limits"),
    ("unsafe release from pit lane", "unsafe release"),
    ("pit lane speeding detected", "pit lane speeding"),
    ("ignoring blue flag signals", "ignoring blue flags"),
    ("impeding Car 16 in qualifying", "impeding"),
    ("false start at race start", "false start"),
    ("weaving under braking", "weaving"),
    ("yellow flag violation in sector 2", "yellow flag violation"),
    ("virtual safety car delta infringement", "VSC infringement"),
    ("nothing here", None),
])
def test_extract_infraction_type(text, expected):
    assert extract_infraction_type(text) == expected


# ---------------------------------------------------------------------------
# extract_incident (full record)
# ---------------------------------------------------------------------------

def test_extract_incident_full():
    record = {
        "doc_id": "test-001",
        "title": "Causing a collision — Car 44",
        "raw_text": (
            "During the Race on lap 12, driver Lewis Hamilton, Car 44, "
            "was found to be causing a collision with Car 63. "
            "The stewards impose a 5 seconds time penalty. "
            "2 penalty points are added to the Superlicence."
        ),
    }
    result = extract_incident(record)
    assert result["doc_id"] == "test-001"
    assert result["car_number"] == 44
    assert result["driver_name"] == "Lewis Hamilton"
    assert result["infraction_type"] == "causing a collision"
    assert result["outcome"] == "5s time penalty"
    assert result["penalty_points"] == 2
    assert result["lap_number"] == 12
    assert result["session_type"] == "race"


def test_extract_incident_nfa():
    record = {
        "doc_id": "test-002",
        "title": "Track limits — Car 16",
        "raw_text": "Qualifying session. Car 16. Track limits at Turn 9. No further action.",
    }
    result = extract_incident(record)
    assert result["car_number"] == 16
    assert result["infraction_type"] == "track limits"
    assert result["outcome"] == "no further action"
    assert result["session_type"] == "qualifying"


def test_extract_incident_missing_fields():
    record = {"doc_id": "test-003", "title": "General Notice", "raw_text": "Nothing specific here."}
    result = extract_incident(record)
    assert result["doc_id"] == "test-003"
    assert result["car_number"] is None
    assert result["driver_name"] is None
    assert result["infraction_type"] is None
    assert result["outcome"] is None


# ---------------------------------------------------------------------------
# batch_extract
# ---------------------------------------------------------------------------

def test_batch_extract():
    records = [
        {
            "doc_id": f"batch-{i}",
            "title": f"Track limits — Car {i}",
            "raw_text": f"Car {i}. Race. Lap {i}. Track limits. 5 seconds time penalty.",
        }
        for i in range(1, 6)
    ]
    results = batch_extract(records)
    assert len(results) == 5
    for i, result in enumerate(results, 1):
        assert result["doc_id"] == f"batch-{i}"
        assert result["infraction_type"] == "track limits"
        assert result["outcome"] == "5s time penalty"


# ---------------------------------------------------------------------------
# Ruling types recovered by the v10 corpus scan
#
# Each string below is real phrasing taken from a stored FIA decision that the
# extractor previously classified as None.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("The lap time is deleted", "deleted lap times"),
    ("Car 4 did not use the track at turn 9", "deleted lap times"),
    ("Forcing another driver off the track", "forcing another driver off the track"),
    ("The driver gained a lasting advantage", "gaining an advantage off track"),
    ("Crossing the track without permission", "crossing the track"),
    ("Breach of parc ferme conditions", "parc ferme breach"),
    ("Parc Fermé", "parc ferme breach"),
    ("Exceeding maximum time between the safety car lines SC2 - SC1",
     "safety car line time limit"),
    ("Failing to maintain the required 10 car lengths", "failing to maintain distance"),
    ("Overtaking under the safety car", "overtaking under safety car"),
    ("Failed to set a time within 107% of the fastest lap", "107% rule"),
    ("Failure to follow the Race Director's instructions",
     "failure to follow Race Director instructions"),
    ("Car 20 allegedly undertook a practice start at pit exit",
     "practice start infringement"),
    ("Car 55 was released in an unsafe condition", "released in an unsafe condition"),
    ("Exceeded the permitted number of PU elements",
     "power unit element infringement"),
    ("Failure to attend the drivers' parade", "driver obligation breach"),
    ("Failing to stop for weighing", "weighing procedure"),
])
def test_extract_infraction_type_recovered_types(text, expected):
    assert extract_infraction_type(text) == expected


def test_new_patterns_do_not_shadow_existing_ones():
    """The new patterns are appended, so established labels must be unchanged."""
    assert extract_infraction_type("causing a collision after leaving the track") == \
        "causing a collision"
    assert extract_infraction_type("track limits at turn 4, lap time deleted") == \
        "track limits"


# ---------------------------------------------------------------------------
# Outcome fixes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Decision 10 Second Stop-and-Go penalty.",
    "Decision 10 second stop and go penalty.",
    "A mandatory Stop-and-Go penalty imposed after the Race.",
])
def test_extract_outcome_stop_and_go(text):
    """Words between the number and 'penalty' used to defeat every rule."""
    assert extract_outcome(text) == "stop-and-go penalty"


@pytest.mark.parametrize("text", [
    "The competitor (Scuderia Ferrari HP) is fined €1000.",
    "The driver George Russell is fined €5.000, suspended for 12 months",
    "is fined €30,000, €20,000 of which is suspended",
])
def test_extract_outcome_fine_currency_prefix(text):
    """The FIA writes the symbol before the amount, not after."""
    assert extract_outcome(text) == "fine"


def test_passing_mention_of_a_deletion_is_not_a_track_limits_ruling():
    """
    Verbatim from doc 34, 2024 Singapore GP. The Infringement is a Race
    Director's Event Notes breach; the Reason merely observes that the driver
    knew a lap time would be deleted. Classifying on that passing mention put
    the ruling in the wrong category.
    """
    # Classification runs on "{title}\n{body}", as extract_incident does.
    text = (
        "Doc 34 - Infringement - Car 55 - Failure to follow Race Director's Instructions\n"
        "Fact Failure to follow the Race Director’s Event Notes. "
        "Infringement Alleged breach of Article 12.2.1 i) of the International "
        "Sporting Code and noncompliance with Race Director’s Event Note. "
        "Reason ... as it was qualifying knew that his lap time would be deleted."
    )
    assert extract_infraction_type(text) == "failure to follow Race Director instructions"


@pytest.mark.parametrize("text,expected", [
    # Genuine driver-obligation rulings, verbatim corpus titles.
    ("Doc 27 - Decision - Car 10 - Late attendance to Drivers' meeting",
     "driver obligation breach"),
    ("Doc 19 - Summons - Car 10 - Late for drivers’ meeting", "driver obligation breach"),
    ("Offence - Car 5 - Behaviour in Drivers' Meeting", "driver obligation breach"),
    ("Doc 49 - Infringement - Car 55 - Late attendance of National Anthem",
     "driver obligation breach"),
    ("Doc 18 - Infringement - Car 18 - Fan Engagement Activity", "driver obligation breach"),
    ("Infringement - Car 20 - Drivers' Parade", "driver obligation breach"),
])
def test_driver_obligation_rulings(text, expected):
    assert extract_infraction_type(text) == expected


def test_passing_mention_of_the_drivers_briefing_is_not_an_obligation_breach():
    """
    Verbatim from doc 37, 2024 Italian GP: an escape-road ruling whose Reason
    happens to mention the drivers' briefing. A bare "drivers' briefing" match
    stole this document — and the yellow-flag and crossing-the-track rulings
    too — from their real categories.
    """
    text = (
        "Doc 37 - Decision - Car 18 - Alleged failure to follow Race Director's "
        "instructions (Escape Road)\n"
        "Fact Car 18 did not follow the Race Director's Event Notes regarding the "
        "escape road instructions at Turns 4/5. "
        "Reason ... there was some confusion following the drivers' briefing as to "
        "where the bollard would be located."
    )
    assert extract_infraction_type(text) == "failure to follow Race Director instructions"


@pytest.mark.parametrize("text,expected", [
    # Titles are the only place several of these rulings name the offence.
    ("Doc 73 - Infringement - Car 5 - Practice Start", "practice start infringement"),
    ("Summons - Car 1 - Alleged practice start infringement", "practice start infringement"),
    ("Car 63 performed a practice start outside the designated practice start area",
     "practice start infringement"),
])
def test_practice_start_rulings(text, expected):
    assert extract_infraction_type(text) == expected


def test_practice_start_area_as_a_location_is_not_a_practice_start_ruling():
    """
    Verbatim from doc 30, 2023. The offence is overtaking in the fast lane; the
    Practice Start Area is only where the car was heading, and the Reason even
    notes the driver "did perform a genuine practice start" — lawfully. Matching
    the bare phrase pulled six pit-lane rulings out of their real category.
    """
    text = (
        "Doc 30 - Infringement - Car 81 - Failure to follow Race Director's instructions\n"
        "Fact Car 81 overtook several cars in the Fast Lane whilst traversing the "
        "Working Lane to the Practice Start Area. "
        "Reason ... it was impractical to drive directly from the garage to the "
        "practice start area. The Stewards also accept the driver of Car 81 did in "
        "fact perform a genuine practice start and tried to rejoin."
    )
    assert extract_infraction_type(text) == "failure to follow Race Director instructions"


def test_near_collision_behind_the_safety_car():
    """Article 55.5 rulings state no overtake, so the overtake-only rule missed them."""
    text = (
        "Decision - Car 22 - Incident behind the Safety Car\n"
        "Fact Near collision behind the safety car. "
        "Offence Alleged breach of Article 55.5 of the FIA Formula One Sporting Regulations."
    )
    assert extract_infraction_type(text) == "safety car violation"


# ---------------------------------------------------------------------------
# extract_suspension — imposed vs actually served
# ---------------------------------------------------------------------------

# Verbatim from 2026 Canadian GP document 99. The stop-and-go was never served;
# storing it as a bare "SG" made it identical to one that was.
_SUSPENDED_SG = """
2026 CANADIAN GRAND PRIX
No / Driver 27 - Nico Hulkenberg
Fact Cars 27 and 30 were out of position at Safety Car Line 1 during the
formation lap. Car 27 did not enter the Pit Lane as required by the Regulations.
InfringementBreach of Article B5.6.4 of the FIA F1 Regulations.
Decision A mandatory Stop-and-Go penalty imposed after the Race. This penalty is
suspended for the period ending at the final race of the 2026 Championship on
condition that no further similar breach, by this driver, occurs. In addition the
driver is Reprimanded for failure to start the formation lap in the correct order.
Reason The Stewards heard from the driver of Car 27.
"""

# Verbatim from 2025 Miami GP document 59 — half the fine really was paid.
_SUSPENDED_PART = """
Decision The competitor (Oracle Red Bull Racing) is fined €50,000, €25,000 of which
is suspended for the remainder of the 2025 season on condition that there is no
breach of a similar nature.
Reason The Stewards heard from the team representative.
"""

# A red-flagged session is "suspended" in an entirely unrelated sense, and this
# document imposed no penalty at all.
_SUSPENDED_NOISE = """
Decision No further action.
Reason The Stewards reviewed video evidence. During the Qualifying session, which
was suspended due to a red flag incident, and while the cars were lined up to
leave the pit lane, Car 12 was waiting to blend into the fast lane.
"""

# A Super Licence suspension IS the penalty — a race ban, not a reprieve.
_SUSPENDED_LICENCE = """
Decision The Super Licence of the driver of Car 20 is suspended for the next
Competition of the 2024 FIA Formula One World Championship.
Reason The driver has accrued 12 penalty points.
"""


def test_a_wholly_suspended_penalty_is_recorded_as_full():
    assert extract_suspension(_SUSPENDED_SG) == "full"


def test_a_part_suspended_fine_is_recorded_as_partial():
    assert extract_suspension(_SUSPENDED_PART) == "partial"


def test_a_suspended_session_is_not_a_suspended_penalty():
    assert extract_suspension(_SUSPENDED_NOISE) is None


def test_a_suspended_super_licence_is_a_ban_not_a_reprieve():
    assert extract_suspension(_SUSPENDED_LICENCE) is None


def test_an_ordinary_penalty_is_not_suspended():
    text = "Decision 10 second time penalty and 2 penalty points.\nReason Collision."
    assert extract_suspension(text) is None


@pytest.mark.parametrize(
    ("decision", "expected"),
    [
        # Single amount immediately followed by "suspended" — the whole fine.
        ("The driver is fined €5.000, suspended for a period of 12 months.", "full"),
        ("Fine of €25,000 - Suspended.", "full"),
        ("The competitor is fined €5,000. This fine is suspended for 12 months.", "full"),
        # Two amounts, or an explicit connector — only part of it.
        ("is fined €30,000, €20,000 of which is suspended for a period of 12 months.",
         "partial"),
        ("is fined €25,000 of which €15,000 is suspended for a period of 12 months.",
         "partial"),
        ("is fined €50,000 - with €40,000 suspended.", "partial"),
        ("A fine of €500,000 is imposed. €350,000 of the fine is suspended.", "partial"),
        ("In addition to imposing a significant fine (which is suspended in parts).",
         "partial"),
    ],
)
def test_full_versus_partial_suspension(decision, expected):
    assert extract_suspension(f"Decision {decision}\nReason Because.") == expected


def test_line_broken_connector_still_reads_as_partial():
    """The PDF text layer breaks these sentences mid-phrase.

    "20,000 of\nwhich is suspended" must not read as a total suspension — it
    would claim a fine went unpaid when half of it was paid.
    """
    text = "Decision The competitor is fined €30,000, €20,000 of\nwhich is suspended.\nReason X."
    assert extract_suspension(text) == "partial"


def test_suspension_is_read_even_without_a_decision_heading():
    """Some rulings have no Decision heading at all.

    The 2024 Austin track-invasion fine is laid out as numbered clauses, and the
    suspension would otherwise be missed entirely.
    """
    text = (
        "Description Infringement - Organiser and Promoter - Track Invasion\n"
        "d. A fine of €500,000 is imposed on the Promoter.\n"
        "e. €350,000 of the fine is suspended until December 31 2026.\n"
    )
    assert extract_suspension(text) == "partial"


# ── Event header ─────────────────────────────────────────────────────────────

def test_event_header_reads_name_and_dates() -> None:
    text = (
        "2024 AUSTRIAN GRAND PRIX\n"
        "28 - 30 June 2024\n"
        "From The Stewards Document 71\n"
    )
    assert extract_event_header(text) == {
        "season": 2024,
        "event_name": "AUSTRIAN GRAND PRIX",
        "start_date": "2024-06-28",
        "end_date": "2024-06-30",
    }


def test_event_header_handles_a_weekend_crossing_two_months() -> None:
    text = "2019 ABU DHABI GRAND PRIX\n28 November - 1 December 2019\nFrom The Stewards\n"
    h = extract_event_header(text)
    assert h["start_date"] == "2019-11-28"
    assert h["end_date"] == "2019-12-01"


def test_event_header_reassembles_drop_capped_titles() -> None:
    # Some PDFs render each word's initial as a separate drop cap, so the text
    # layer emits the capitals on one line and the remainders on the next.
    text = "2024 U S G P\nNITED TATES RAND RIX\n18 – 20 October 2024\nFrom The Stewards\n"
    h = extract_event_header(text)
    assert h["event_name"] == "UNITED STATES GRAND PRIX"
    assert h["season"] == 2024


def test_event_header_accepts_the_one_event_printed_without_a_year() -> None:
    # The 2020 70th Anniversary GP carries no year above its dates.
    text = "70TH ANNIVERSARY GRAND PRIX\n6 – 9 August 2020\nFrom The FIA Technical Delegate\n"
    h = extract_event_header(text)
    assert h == {
        "season": 2020,
        "event_name": "70TH ANNIVERSARY GRAND PRIX",
        "start_date": "2020-08-06",
        "end_date": "2020-08-09",
    }


def test_event_header_survives_a_missing_date_line() -> None:
    h = extract_event_header("2023 SINGAPORE GRAND PRIX\nFrom The Stewards Document 12\n")
    assert h["event_name"] == "SINGAPORE GRAND PRIX"
    assert h["start_date"] is None and h["end_date"] is None


def test_event_header_ignores_a_race_named_in_the_body() -> None:
    # A right-of-review decision discusses an earlier round; only the header
    # states which weekend the document itself belongs to.
    text = (
        "2024 QATAR GRAND PRIX\n29 November - 1 December 2024\nFrom The Stewards\n"
        + "x" * 500
        + "\n2024 AUSTRIAN GRAND PRIX\n"
    )
    assert extract_event_header(text)["event_name"] == "QATAR GRAND PRIX"


def test_event_header_returns_none_when_there_is_no_header() -> None:
    assert extract_event_header("Competitors are reminded of Article 15.") is None


# ── Grid penalties and the pit lane start ────────────────────────────────────

@pytest.mark.parametrize("decision,expected", [
    ("Decision Drop of 5 grid positions for the next Race.", 5),
    ("Decision Drop of 10 grid positions for the next Race.", 10),
    ("Decision 5 grid place penalty for the Race.", 5),
    ("Decision 10 place grid penalty for the Race.", 10),
    ("Decision Drop of 1 grid position for the next Race.", 1),
    # The FIA spells the number out at least as often as it prints a digit.
    ("Decision A drop of three grid positions for the next race.", 3),
    ("Decision We impose a one position grid penalty.", 1),
    ("Decision 10 second time penalty.", None),
])
def test_extract_grid_positions(decision, expected):
    assert extract_grid_positions(decision + "\nReason The car was impeded.") == expected


def test_grid_size_is_not_read_from_a_penalty_the_stewards_declined():
    # The Reason routinely names the standard penalty in order to depart from
    # it. Reading the whole document records the number they did NOT impose.
    text = (
        "Decision Warning.\n"
        "Reason The standard penalty for impeding during Qualifying in the "
        "Penalty Guidelines is a 3 grid position penalty, however in mitigation "
        "the Stewards issue a warning instead.\n"
    )
    assert extract_grid_positions(text) is None
    assert extract_outcome(text) == "warning"


def test_a_starting_grid_position_in_the_narrative_is_not_a_penalty():
    text = (
        "Decision No further action.\n"
        "Reason Car 27 was slower than expected, starting from its grid "
        "position for what would be a third formation lap.\n"
    )
    assert extract_grid_positions(text) is None


def test_a_pit_lane_start_is_its_own_penalty():
    text = (
        "Fact Changes were made to the car during parc ferme.\n"
        "Decision Required to start the Race from the pit lane.\n"
        "Reason This replaces the grid penalty that would otherwise apply.\n"
    )
    assert extract_outcome(text) == "pit lane start"
    # ...and must not be read as the grid penalty its Reason mentions.
    assert extract_grid_positions(text) is None


def test_outcome_comes_from_the_decision_not_the_reason():
    # A failure-to-serve whose Decision is a time penalty, whose Reason weighs
    # and rejects disqualification. The Reason used to win.
    text = (
        "Decision 10 second time penalty.\n"
        "Reason The Stewards considered disqualification but determined that a "
        "time penalty was the appropriate sanction.\n"
    )
    assert extract_outcome(text) == "10s time penalty"


def test_outcome_falls_back_to_the_whole_document_without_a_decision_heading():
    assert extract_outcome("The Stewards impose a reprimand on the driver.") == "reprimand"


# ── The Reason section ────────────────────────────────────────────────────────

_APPEAL_BOILERPLATE = (
    "Competitors are reminded that they have the right to appeal certain "
    "decisions of the Stewards, in accordance with Article 15 of the FIA "
    "International Sporting Code and Chapter 4 of the FIA Judicial and "
    "Disciplinary Rules, within the applicable time limits.\n"
    "Decisions of the Stewards are taken independently of the FIA and are "
    "based solely on the relevant regulations, guidelines and evidence "
    "presented.\n"
    "Gerd Ennser Andrew Mallalieu\n"
    "Johnny Herbert Luciano Burti\n"
    "The Stewards"
)


def test_reason_starts_at_the_reason_heading_not_the_header():
    # "The Stewards, having received a report..." opens every decision. The old
    # marker search found it and began there, so the stored reasoning was the
    # header and the facts rather than the argument.
    text = (
        "The Stewards, having received a report from the Race Director, have "
        "considered the following matter.\n"
        "Fact Car 16 used unsuitable language.\n"
        "Decision Fine of €10,000.\n"
        "Reason The Stewards considered the mitigation that Leclerc "
        "apologised immediately.\n"
    )
    reason = extract_reason(text)
    assert reason.startswith("The Stewards considered the mitigation")
    assert "Race Director" not in reason
    assert "Fact Car 16" not in reason


def test_the_appeal_boilerplate_and_signatures_are_stripped():
    text = "Reason The driver was found to be at fault.\n" + _APPEAL_BOILERPLATE
    reason = extract_reason(text)
    assert reason == "The driver was found to be at fault."


def test_the_operative_reasoning_survives_in_full():
    # The 2024 Mexican GP misconduct case: the old 2,000-char cut lost the
    # mitigation and the fine, which is the entire point of the document.
    text = (
        "The Stewards, having received a report from the Race Director.\n"
        + "Fact Filler sentence about the matter. " * 60
        + "\nDecision Fine of €10,000.\n"
        "Reason The Stewards considered the mitigation factor that Leclerc was "
        "immediately apologetic and chose to levy a fine of €10,000 with "
        "€5,000 suspended pending no repeat within 12 months.\n"
        + _APPEAL_BOILERPLATE
    )
    reason = extract_reason(text)
    assert "€10,000 with €5,000 suspended" in reason
    assert "Filler sentence" not in reason


def test_a_document_with_no_reason_heading_falls_back_to_its_text():
    # Administrative sheets carry no argument; returning nothing would drop
    # them from the corpus silently.
    text = "PU elements used per driver up to now.\nCar 1 Engine 3 of 4."
    assert "PU elements" in extract_reason(text)


def test_a_runaway_reason_is_cut_at_a_sentence_end():
    text = "Reason " + ("The stewards reviewed the video evidence carefully. " * 300)
    reason = extract_reason(text)
    assert len(reason) <= 6000
    assert reason.endswith(".")


def test_reason_of_empty_text_is_empty():
    assert extract_reason("") == ""


# ---------------------------------------------------------------------------
# extract_contact — did the cars actually touch
# ---------------------------------------------------------------------------

def _fact(text: str) -> str:
    return f"Fact {text} InfringementBreach of Appendix L. Decision 5 second penalty."


@pytest.mark.parametrize("fact,expected", [
    ("Car 63 collided with Car 1 at Turn 12.",                       True),
    ("Cars 44 and 33 collided in Turn 10.",                          True),
    ("Collision with Car 11 after Turn 2.",                          True),
    ("Unsafe release of Car 31 and collision with Car 16.",          True),
    ("Car 5 made contact with Car 30 on the exit of Turn 4.",        True),
    # No contact involved in the offence at all.
    ("Exceeding track limits at Turn 9.",                            False),
    ("Speeding in the pit lane during Practice 1.",                  False),
    ("Unnecessarily impeding car 2 between Turns 17 and 18.",        False),
    ("Left and rejoined the track in an unsafe manner at turn 5.",   False),
    # Same word, opposite meaning.
    ("Near collision behind the safety car.",                        False),
    ("The Stewards determined there was no contact between the cars.", False),
])
def test_extract_contact(fact, expected):
    assert extract_contact(_fact(fact)) is expected


def test_incident_between_cars_settles_nothing():
    """The FIA's neutral opener covers a crash and a near miss equally. It is
    not evidence of contact, and it is not evidence of none."""
    assert extract_contact(_fact("Incident between cars 14 & 55 in Turn 9.")) is None


def test_contact_needs_a_fact_section():
    assert extract_contact("Decision - Car 4 - Collision. Reason The Stewards.") is None


# ---------------------------------------------------------------------------
# extract_incident_time — the second Time, not the letterhead's
# ---------------------------------------------------------------------------

_TIMED_DOC = """2026 MONACO GRAND PRIX
From The Stewards Document 89
To The Team Manager, Date 07 June 2026
Audi Revolut F1 Team
Time 20:24
The Stewards, having received a report from the Race Director, have considered
the following matter and determine the following:
No / Driver 27 - Nico Hulkenberg
Competitor Audi Revolut F1 Team
Time 17:17
Session Race
Fact Car 27 collided with Car 55 in Turn 8
"""


def test_incident_time_is_not_the_publication_time():
    """20:24 is when the FIA published; 17:17 is when the incident happened.
    Taking the first Time dates every incident to hours after the flag."""
    assert extract_incident_time(_TIMED_DOC) == (17, 17)


# A ruling covering many drivers at once has no incident block, so the only
# Time it prints is the letterhead's. Structure taken verbatim from the 2025
# Italian Grand Prix Document 41: the letterhead repeats on the second page,
# and the preamble sits between it and the Session field.
_MULTI_DRIVER_DOC = """2025 ITALIAN GRAND PRIX
From The Stewards Document 41
To All Teams, All Officials Date 07 September 2025
Time 17:05
Title Infringement - Race Deleted Lap Times
2025 I G P
From The Stewards Document 41
To All Officials, All Teams Date 07 September 2025
Time 17:05
The Stewards, having received a report from the Race Director, have considered
and determine the following:
Session Race
Fact The cars below did not use the track at turns 1, 2, 4, 5, and 7
No Turn Car Driver Competitor Time of Day Lap Time
1 4 18 Lance Stroll Aston Martin Aramco F1 Team 15:05:41 1:26.506
2 1 16 Charles Leclerc Scuderia Ferrari HP 15:08:05 1:24.525
"""


def test_a_notice_with_only_a_publication_time_yields_none():
    """17:05 is when the FIA issued the document — over an hour after the race.

    The incident Time sits directly above Session, and this document has none
    because it rules on twenty-one deletions at once. Taking the letterhead
    put the incident after the session's last race control message on 34 of
    40 documents checked, and the real deletion times are in the table below.
    """
    assert extract_incident_time(_MULTI_DRIVER_DOC) is None


def test_the_preamble_is_what_separates_the_letterhead_from_an_incident_time():
    """The same document with an incident block does report its time."""
    with_block = _MULTI_DRIVER_DOC.replace(
        "The Stewards, having received a report from the Race Director, have considered\n"
        "and determine the following:\n",
        "No / Driver 18 - Lance Stroll\nCompetitor Aston Martin Aramco F1 Team\nTime 15:05\n",
    )
    assert extract_incident_time(with_block) == (15, 5)


def test_no_session_field_means_no_anchor_for_the_time():
    assert extract_incident_time("From The Stewards\nTime 18:42\nDecision X") is None


def test_impossible_clock_readings_are_rejected():
    assert extract_incident_time("Time 47:99\nSession Race\n") is None


# ---------------------------------------------------------------------------
# extract_table_subjects — rulings that name their drivers in a table
# ---------------------------------------------------------------------------

# Verbatim shape of a deleted-lap-times ruling. The columns collapse together
# in the PDF text layer, so the driver and the team arrive as one run, and the
# team is full of digits ("Stake F1 Team") — which is why the name cannot be
# matched as "everything up to the next number".
_DELETED_LAPS = """Session Race
Fact The cars below did not use the track at turns 2, 4 and 12.
No Turn Car Driver Competitor Time of Day Lap Time
1 4 24 Zhou Guanyu Stake F1 Team Kick Sauber 12:56:34 1:29.677
2 2 43 Franco Colapinto Williams Racing 12:57:37 1:27.143
3 12 44 Lewis Hamilton Mercedes-AMG PETRONAS F1 Team 13:05:45 1:31.858
4 2 43 Franco Colapinto Williams Racing 13:09:01 1:24.750
Decision Deletion of the lap times shown.
"""


def test_table_ruling_names_every_driver_once():
    """The table has one row per deleted lap, so a driver appears repeatedly
    and must be returned once, in the order the table first names them."""
    assert extract_table_subjects(_DELETED_LAPS) == [
        (24, "Zhou Guanyu"),
        (43, "Franco Colapinto"),
        (44, "Lewis Hamilton"),
    ]


def test_a_single_row_table_still_names_its_driver():
    one_row = ("Fact The car below exceeded the 1:14.0-time limit.\n"
               "No Car Driver Competitor Time of Day Lap\n"
               "1 18 Lance Stroll Aston Martin Aramco Cognizant F1 Team 15:32:08 8 (Q1)\n")
    assert extract_table_subjects(one_row) == [(18, "Lance Stroll")]


def test_penalty_table_layout_is_read_too():
    """One document, several drivers, a real penalty each — and no subject
    header anywhere in it."""
    penalties = ("Decision Penalties below imposed after the race.\n"
                 "No No / Driver Competitor Penalty\n"
                 "1 55 - Carlos Sainz Scuderia Ferrari 10 second time penalty\n"
                 "2 44 - Lewis Hamilton Mercedes AMG-Petronas F1 Team 10 second time penalty\n"
                 "3 31 - Esteban Ocon BWT Alpine F1 Team 5 second time penalty\n")
    assert extract_table_subjects(penalties) == [
        (55, "Carlos Sainz"),
        (44, "Lewis Hamilton"),
        (31, "Esteban Ocon"),
    ]


def test_a_numbered_list_without_a_table_header_is_not_a_table():
    """The row pattern alone matches ordinary numbered prose. The header is
    what makes it a table, and without it nothing is claimed."""
    prose = ("Fact The Stewards considered the following:\n"
             "1 The driver reported at 14:30 as required.\n"
             "2 The team confirmed at 15:10 that the car was compliant.\n")
    assert extract_table_subjects(prose) == []


def test_a_lowercase_particle_belongs_to_the_name():
    text = ("No Turn Car Driver Competitor Time of Day Lap Time\n"
            "1 4 21 Nyck de Vries Scuderia AlphaTauri 14:02:11 1:31.402\n")
    assert extract_table_subjects(text) == [(21, "Nyck de Vries")]


# ---------------------------------------------------------------------------
# extract_video_refs
# ---------------------------------------------------------------------------
# The FIA writes the evidence sentence to a near-fixed formula, so these are
# the real shapes it takes across the corpus rather than invented ones.
@pytest.mark.parametrize("text,expected", [
    ("Reason The Stewards reviewed video evidence.", ["video"]),
    ("Reason The Stewards reviewed video, in-car video evidence.",
     ["video", "in-car video"]),
    ("Reason The Stewards reviewed positioning/marshalling system data, video,"
     " timing, team radio and in-car video evidence.", ["video", "in-car video"]),
    ("Reason The Stewards examined CCTV cameras and video evidence.",
     ["video", "cctv"]),
    # The PDF text layer breaks hyphenated words across a line.
    ("Reason The Stewards reviewed in- car video evidence.", ["in-car video"]),
    ("Reason The Stewards reviewed on-board cameras.", ["in-car video"]),
])
def test_extract_video_refs(text, expected):
    assert extract_video_refs(text) == expected


def test_evidence_that_is_not_vision_is_not_stored():
    """Telemetry and radio are listed in the same sentence and belong elsewhere."""
    text = ("Reason The Stewards heard from the driver of Car 44 and reviewed"
            " positioning/marshalling system data, timing, telemetry and team radio.")
    assert extract_video_refs(text) is None


def test_a_named_camera_does_not_also_report_generic_video():
    """"in-car video" contains the word "video"; it must be read once, not twice."""
    text = "Reason The Stewards reviewed in-car video evidence."
    assert extract_video_refs(text) == ["in-car video"]


def test_video_must_have_been_reviewed_to_count():
    """Narrative mentions are not evidence the stewards examined."""
    text = ("Reason The driver stated that he had seen the video on television"
            " after the race and disagreed with it.")
    assert extract_video_refs(text) is None


def test_a_document_naming_no_evidence_yields_none():
    """None, not [], so "reviewed no video" stays distinct from "does not say"."""
    assert extract_video_refs("Reason The car was underweight.") is None
