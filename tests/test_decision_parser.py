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
