"""Tests for packages.pipeline.parsers.decision_parser."""

import pytest

from packages.pipeline.parsers.decision_parser import (
    batch_extract,
    extract_car_number,
    extract_driver_name,
    extract_event_header,
    extract_grid_positions,
    extract_incident,
    extract_infraction_type,
    extract_involved_cars,
    extract_lap_number,
    extract_outcome,
    extract_penalty_points,
    extract_session_type,
    extract_subjects,
    extract_suspension,
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
    ("FP1 Practice incident", "practice"),
    ("Formation lap violation", "formation lap"),
    ("nothing relevant", None),
])
def test_extract_session_type(text, expected):
    assert extract_session_type(text) == expected


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
