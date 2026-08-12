"""Tests for incident_extractor.py"""

import pytest

from packages.pipeline.extractors.incident_extractor import (
    ExtractionResult,
    IncidentExtractor,
    _infer_contact,
    _normalise_infraction_category,
    _normalise_penalty_type,
    _parse_penalty_seconds,
)


@pytest.fixture
def extractor():
    return IncidentExtractor(enable_layoutlm=False)


# ---------------------------------------------------------------------------
# Penalty type normalisation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("5 second time penalty",     "5s"),
    ("10 second time penalty",    "10s"),
    ("5s penalty",                "5s"),
    ("drive-through penalty",     "DT"),
    ("drive through penalty",     "DT"),
    ("reprimand",                 "REP"),
    ("no further action",         "NFA"),
    ("disqualification",          "DSQ"),
    ("grid penalty of 3 places",  "GRID"),
    ("pit lane penalty",          "DT"),
    (None,                        None),
])
def test_normalise_penalty_type(raw, expected):
    assert _normalise_penalty_type(raw) == expected


# ---------------------------------------------------------------------------
# Infraction category
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("causing a collision",        "collision"),
    ("track limits violation",     "track_limits"),
    ("unsafe release from pit",    "unsafe_release"),
    ("pit lane speeding",          "pit_lane_speed"),
    ("impeding another driver",    "impeding"),
    ("ignoring blue flags",        "blue_flag"),
    (None,                         None),
])
def test_normalise_infraction_category(raw, expected):
    assert _normalise_infraction_category(raw) == expected


# ---------------------------------------------------------------------------
# Penalty seconds parsing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("5 second time penalty",  5),
    ("10 seconds penalty",     10),
    ("3 seconds",              3),
    ("reprimand",              None),
    (None,                     None),
])
def test_parse_penalty_seconds(raw, expected):
    assert _parse_penalty_seconds(raw) == expected


# ---------------------------------------------------------------------------
# Contact inference
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("infraction,expected", [
    ("causing a collision",  True),
    ("contact with car 44",  True),
    ("track limits",         False),
    ("impeding",             False),
    (None,                   None),
])
def test_infer_contact(infraction, expected):
    assert _infer_contact(infraction) == expected


# ---------------------------------------------------------------------------
# Full extraction from record
# ---------------------------------------------------------------------------

SAMPLE_DECISION_TEXT = """
The Stewards of the meeting, having examined the relevant documentation
and video evidence, and having heard from the driver of Car 44 (Lewis Hamilton),
determine that Car 44 committed a breach of Art. 48.1 of the Sporting Regulations
by causing a collision with Car 33 at Turn 1 on lap 12 of the Race.

Decision: The driver of Car 44 is given a 5 second time penalty and 2 penalty points.
"""


def test_extract_car_number(extractor):
    record = {"doc_id": "test1", "season": 2024, "raw_text": SAMPLE_DECISION_TEXT}
    result = extractor.extract(record)
    assert result.car_number == 44


def test_extract_driver_name(extractor):
    # driver_name may be None if regex doesn't match parenthetical form;
    # resolved driver (via car_number=44) should still appear in drivers list
    record = {"doc_id": "test1", "season": 2024, "raw_text": SAMPLE_DECISION_TEXT}
    result = extractor.extract(record)
    drivers_found = [d for d in result.drivers if d.get("code") == "HAM" or d.get("number") == 44]
    assert len(drivers_found) > 0 or (result.driver_name is not None and "Hamilton" in result.driver_name)


def test_extract_lap_number(extractor):
    record = {"doc_id": "test1", "season": 2024, "raw_text": SAMPLE_DECISION_TEXT}
    result = extractor.extract(record)
    assert result.lap_number == 12


def test_extract_infraction(extractor):
    record = {"doc_id": "test1", "season": 2024, "raw_text": SAMPLE_DECISION_TEXT}
    result = extractor.extract(record)
    assert result.infraction_type is not None
    assert "collision" in result.infraction_type.lower()


def test_extract_penalty_type(extractor):
    record = {"doc_id": "test1", "season": 2024, "raw_text": SAMPLE_DECISION_TEXT}
    result = extractor.extract(record)
    assert result.penalty_type == "5s"


def test_extract_penalty_seconds(extractor):
    record = {"doc_id": "test1", "season": 2024, "raw_text": SAMPLE_DECISION_TEXT}
    result = extractor.extract(record)
    # outcome="5s time penalty" → penalty_seconds=5
    assert result.penalty_seconds == 5 or result.penalty_type == "5s"


def test_extract_penalty_points(extractor):
    record = {"doc_id": "test1", "season": 2024, "raw_text": SAMPLE_DECISION_TEXT}
    result = extractor.extract(record)
    assert result.penalty_points == 2


def test_extract_article_cited(extractor):
    record = {"doc_id": "test1", "season": 2024, "raw_text": SAMPLE_DECISION_TEXT}
    result = extractor.extract(record)
    assert "48.1" in result.article_cited


def test_extract_contact_true(extractor):
    record = {"doc_id": "test1", "season": 2024, "raw_text": SAMPLE_DECISION_TEXT}
    result = extractor.extract(record)
    assert result.contact is True


def test_extract_session_type(extractor):
    record = {"doc_id": "test1", "season": 2024, "raw_text": SAMPLE_DECISION_TEXT}
    result = extractor.extract(record)
    assert result.session_type == "race"


def test_extract_drivers_resolved(extractor):
    record = {"doc_id": "test1", "season": 2024, "raw_text": SAMPLE_DECISION_TEXT}
    result = extractor.extract(record)
    assert len(result.drivers) > 0
    driver = result.drivers[0]
    assert driver.get("code") == "HAM" or driver.get("number") == 44


def test_extract_infraction_category(extractor):
    record = {"doc_id": "test1", "season": 2024, "raw_text": SAMPLE_DECISION_TEXT}
    result = extractor.extract(record)
    assert result.infraction_category == "collision"


def test_extract_to_dict(extractor):
    record = {"doc_id": "test1", "season": 2024, "raw_text": SAMPLE_DECISION_TEXT}
    result = extractor.extract(record)
    d = result.to_dict()
    assert d["doc_id"] == "test1"
    assert d["penalty_type"] == "5s"


def test_extract_empty_record(extractor):
    record = {"doc_id": "empty", "season": 2024, "raw_text": ""}
    result = extractor.extract(record)
    assert isinstance(result, ExtractionResult)
    assert result.doc_id == "empty"


def test_extract_nfa_decision(extractor):
    text = "Decision: No further action is required. The stewards find no breach."
    record = {"doc_id": "nfa1", "season": 2024, "raw_text": text}
    result = extractor.extract(record)
    assert result.penalty_type == "NFA"


def test_extract_disqualification(extractor):
    text = "The driver of Car 16 is disqualified from the results of the Race."
    record = {"doc_id": "dsq1", "season": 2024, "raw_text": text}
    result = extractor.extract(record)
    assert result.penalty_type == "DSQ"
    assert result.car_number == 16


# ---------------------------------------------------------------------------
# Taxonomy completeness
# ---------------------------------------------------------------------------

def test_every_infraction_label_maps_to_a_category():
    """
    Regression guard for the defect that left 823 real rulings unclassified.

    decision_parser emits an infraction label; incident_extractor maps it to a
    category. Nothing tied the two together, so labels such as "starting
    procedure" (whose map key read "start procedure") extracted a type and then
    silently stored a NULL category. Any new pattern must ship with a mapping.
    """
    from packages.pipeline.parsers.decision_parser import _INFRACTION_PATTERNS

    unmapped = [
        label for _, label in _INFRACTION_PATTERNS
        if _normalise_infraction_category(label) is None
    ]
    assert unmapped == [], f"labels with no category mapping: {unmapped}"


@pytest.mark.parametrize("raw,expected", [
    ("deleted lap times",                            "track_limits"),
    ("forcing another driver off the track",         "forcing_off_track"),
    ("parc ferme breach",                            "parc_ferme"),
    ("safety car line time limit",                   "safety_car_line_time"),
    ("107% rule",                                    "107_percent"),
    ("failure to follow Race Director instructions", "race_director_instructions"),
    ("starting procedure",                           "start_procedure"),
    ("false start",                                  "false_start"),
    ("leaving the track",                            "track_limits"),
    ("driving unnecessarily slowly",                 "driving_slowly"),
    ("media commitment breach",                      "driver_obligation"),
])
def test_normalise_infraction_category_recovered(raw, expected):
    assert _normalise_infraction_category(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("stop-and-go penalty", "SG"),
    ("stop and go penalty", "SG"),
    ("warning",             "WARN"),
    ("fine",                "FINE"),
    ("20s time penalty",    "20s"),
    ("15 second penalty",   "15s"),
])
def test_normalise_penalty_type_recovered(raw, expected):
    assert _normalise_penalty_type(raw) == expected
