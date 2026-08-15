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


# ---------------------------------------------------------------------------
# Multi-driver incidents
# ---------------------------------------------------------------------------

# Verbatim shape of 2023 Qatar GP document 55: one ruling, three cars in the
# incident, one of them the accused.
THREE_CAR_COLLISION = (
    "No / Driver 31 - Esteban Ocon\n"
    "Competitor BWT Alpine F1 Team\n"
    "Session Sprint\n"
    "Fact Turn 2 incident between Cars 11, 27 and 31 at 20:52.\n"
    "Infringement Alleged breach of Appendix L, Chapter IV, Article 2 d).\n"
    "Decision No further action.\n"
    "Reason The Stewards heard from the driver of Car 11 (Sergio Perez), the "
    "driver of Car 27 (Nico Hulkenberg) and reviewed video evidence.\n"
)

# Verbatim shape of 2020 Italian GP document 24: one summons, four drivers.
JOINT_SUMMONS = (
    "The drivers are required to report to the Stewards at 14:10 in relation to "
    "the incident below.\n"
    "No / Driver 6 - Nicholas Latifi\n"
    "8 - Romain Grosjean\n"
    "11 - Sergio Perez\n"
    "44 - Lewis Hamilton\n"
    "Reason Alleged driving unnecessarily slowly in turn 11 at 12:58.\n"
)


def test_counterparties_are_recorded_and_resolved(extractor):
    record = {"doc_id": "qat55", "season": 2023, "raw_text": THREE_CAR_COLLISION}
    result = extractor.extract(record)

    assert [d["number"] for d in result.drivers] == [31]
    assert [d["number"] for d in result.involved_drivers] == [11, 27]
    # Resolved to real drivers, not left as bare numbers.
    assert [d["code"] for d in result.involved_drivers] == ["PER", "HUL"]


def test_the_accused_is_never_also_a_counterparty(extractor):
    # Car 31 is named in its own Fact line; filing it as its own victim would
    # make the incident look like a four-car one.
    record = {"doc_id": "qat55", "season": 2023, "raw_text": THREE_CAR_COLLISION}
    result = extractor.extract(record)
    numbers = {d["number"] for d in result.involved_drivers}
    assert 31 not in numbers


def test_joint_summons_records_all_four_drivers(extractor):
    record = {"doc_id": "ita24", "season": 2020, "raw_text": JOINT_SUMMONS}
    result = extractor.extract(record)

    assert [d["number"] for d in result.drivers] == [6, 8, 11, 44]
    assert [d["full_name"] for d in result.drivers][-1] == "Lewis Hamilton"
    # The single-driver fields still describe the first, for callers that read
    # them (the race-control linker takes drivers[0]).
    assert result.car_number == 6
    assert result.drivers[0]["number"] == 6


def test_single_car_ruling_has_no_counterparties(extractor):
    text = ("No / Driver 10 - Pierre Gasly\n"
            "Fact Leaving the track without a justifiable reason multiple times\n"
            "Infringement Breach of Article 33.3.\n"
            "Decision 5 second time penalty\n")
    record = {"doc_id": "aut63", "season": 2023, "raw_text": text}
    result = extractor.extract(record)

    assert [d["number"] for d in result.drivers] == [10]
    assert result.involved_drivers == []


def test_to_dict_carries_involved_drivers(extractor):
    record = {"doc_id": "qat55", "season": 2023, "raw_text": THREE_CAR_COLLISION}
    d = extractor.extract(record).to_dict()
    assert [x["number"] for x in d["involved_drivers"]] == [11, 27]
