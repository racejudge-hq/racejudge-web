"""Tests for packages.pipeline.parsers.decision_parser."""

import pytest

from packages.pipeline.parsers.decision_parser import (
    batch_extract,
    extract_car_number,
    extract_driver_name,
    extract_incident,
    extract_infraction_type,
    extract_lap_number,
    extract_outcome,
    extract_penalty_points,
    extract_session_type,
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
])
def test_extract_car_number(text, expected):
    assert extract_car_number(text) == expected


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
    ("The lap time achieved on lap 12 is deleted", "deleted lap times"),
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
    ("Practice start performed outside the designated area",
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
