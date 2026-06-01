"""Tests for packages.ml.features — feature extraction for penalty prediction."""

import pytest

from packages.ml.features import (
    PENALTY_CLASS_TO_IDX,
    PENALTY_CLASSES,
    _lap_phase,
    _norm_session,
    _norm_tyre,
    _norm_weather,
    _outcome_to_class,
    batch_extract_features,
    extract_features,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def test_penalty_classes_complete():
    assert set(PENALTY_CLASSES) == {"NFA", "REP", "5s", "10s", "DT", "GRID", "DSQ"}
    assert len(PENALTY_CLASS_TO_IDX) == len(PENALTY_CLASSES)


@pytest.mark.parametrize("lap,total,expected", [
    (1, 60, "early"),
    (20, 60, "early"),
    (21, 60, "mid"),
    (40, 60, "mid"),
    (41, 60, "late"),
    (60, 60, "late"),
    (None, 60, "unknown"),
    (10, None, "unknown"),
])
def test_lap_phase(lap, total, expected):
    assert _lap_phase(lap, total) == expected


@pytest.mark.parametrize("s,expected", [
    ("race", "race"),
    ("QUALIFYING", "qualifying"),
    ("Sprint Race", "sprint"),
    ("Practice", "practice"),
    ("formation lap", "formation lap"),
    ("unknown session", "unknown"),
    (None, "unknown"),
])
def test_norm_session(s, expected):
    assert _norm_session(s) == expected


@pytest.mark.parametrize("t,expected", [
    ("SOFT", "soft"),
    ("Medium", "medium"),
    ("HARD", "hard"),
    ("Intermediate", "intermediate"),
    ("WET", "wet"),
    (None, "unknown"),
    ("unknown compound", "unknown"),
])
def test_norm_tyre(t, expected):
    assert _norm_tyre(t) == expected


@pytest.mark.parametrize("w,expected", [
    ("dry", "dry"),
    ("WET", "wet"),
    ("mixed", "mixed"),
    (None, "unknown"),
])
def test_norm_weather(w, expected):
    assert _norm_weather(w) == expected


@pytest.mark.parametrize("outcome,expected_class", [
    ("no further action", "NFA"),
    ("reprimand", "REP"),
    ("5 seconds time penalty", "5s"),
    ("5s time penalty", "5s"),
    ("10s time penalty", "10s"),
    ("drive-through penalty", "DT"),
    ("drive through penalty", "DT"),
    ("grid penalty", "GRID"),
    ("disqualification", "DSQ"),
    ("disqualified", "DSQ"),
    (None, None),
    ("warning", None),
])
def test_outcome_to_class(outcome, expected_class):
    assert _outcome_to_class(outcome) == expected_class


# ---------------------------------------------------------------------------
# extract_features
# ---------------------------------------------------------------------------

def test_extract_features_full():
    record = {
        "doc_id": "test-001",
        "season": 2024,
        "parsed": {
            "infraction_type": "causing a collision",
            "outcome": "5 seconds time penalty",
            "session_type": "race",
            "lap_number": 20,
            "penalty_points": 2,
            "driver_name": "Lewis Hamilton",
            "car_number": 44,
        },
        "total_laps": 60,
        "article_cited": "Art 38.1",
        "corner_type": "high_speed",
        "position_change": -1,
        "safety_car_out": False,
        "openf1": {
            "weather_data": {"rainfall": False},
            "laps": [{"compound": "SOFT"}],
        },
        "telemetry_features": {
            "speed_diff_kph": 25.5,
            "braking_point_delta_m": 12.0,
            "overlap_s": 0.3,
            "drs_deployed": True,
        },
        "driver_history": {
            "penalty_points_ytd": 4,
            "repeat_infraction": False,
        },
    }
    feat = extract_features(record)

    assert feat["doc_id"] == "test-001"
    assert feat["season"] == 2024
    assert feat["infraction_type"] == "causing a collision"
    assert feat["session_type"] == "race"
    assert feat["lap_phase"] == "early"
    assert feat["article_cited"] == "Art 38.1"
    assert feat["corner_type"] == "high_speed"
    assert feat["speed_diff_kph"] == 25.5
    assert feat["drs_deployed"] == 1
    assert feat["weather"] == "dry"
    assert feat["tyre_compound"] == "soft"
    assert feat["penalty_points_ytd"] == 4
    assert feat["penalty_class"] == "5s"
    assert feat["penalty_class_idx"] == PENALTY_CLASS_TO_IDX["5s"]
    assert feat["penalty_points_delta"] == 2


def test_extract_features_minimal():
    record = {"doc_id": "minimal", "season": 2023}
    feat = extract_features(record)
    assert feat["doc_id"] == "minimal"
    assert feat["infraction_type"] == "unknown"
    assert feat["session_type"] == "unknown"
    assert feat["lap_phase"] == "unknown"
    assert feat["speed_diff_kph"] == 0.0
    assert feat["penalty_class"] is None
    assert feat["penalty_class_idx"] == -1


def test_extract_features_nfa():
    record = {
        "doc_id": "nfa-001",
        "season": 2024,
        "parsed": {"outcome": "no further action", "infraction_type": "track limits"},
    }
    feat = extract_features(record)
    assert feat["penalty_class"] == "NFA"


# ---------------------------------------------------------------------------
# batch_extract_features
# ---------------------------------------------------------------------------

def test_batch_extract_features():
    records = [
        {"doc_id": f"b{i}", "season": 2024, "parsed": {"outcome": "reprimand"}}
        for i in range(5)
    ]
    feats = batch_extract_features(records)
    assert len(feats) == 5
    for f in feats:
        assert f["penalty_class"] == "REP"
