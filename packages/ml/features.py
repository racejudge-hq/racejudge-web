"""
Tabular feature extraction for penalty prediction — Phase 5 prep.

Extracts the feature vector described in IMPLEMENTATION_PLAN.md Model 4A
from an incident record (enriched with parser + OpenF1 + telemetry data).

Feature groups:
  - Infraction context: article_cited, lap_phase, session_type, corner_type
  - Driving dynamics: speed_diff, braking_point_delta, overlap_duration
  - Race context: position_change, weather, tyre_compound, safety_car_out
  - History: driver_penalty_points_ytd, team_repeat_infraction
  - Outcome label: penalty_class (7-class target)

Usage:
    from packages.ml.features import extract_features, PENALTY_CLASSES
    vec = extract_features(incident_record)
    # vec is a dict suitable for pandas / xgboost DMatrix
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PENALTY_CLASSES = ["NFA", "REP", "5s", "10s", "DT", "GRID", "DSQ"]
PENALTY_CLASS_TO_IDX = {c: i for i, c in enumerate(PENALTY_CLASSES)}

SESSION_TYPES = ["sprint", "qualifying", "race", "practice", "formation lap"]
CORNER_TYPES = ["hairpin", "chicane", "medium", "high_speed", "unknown"]
WEATHER_TYPES = ["dry", "wet", "mixed", "unknown"]
TYRE_COMPOUNDS = ["soft", "medium", "hard", "intermediate", "wet", "unknown"]


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def _norm_session(s: str | None) -> str:
    if not s:
        return "unknown"
    s = s.lower()
    for t in SESSION_TYPES:
        if t in s:
            return t
    return "unknown"


def _norm_tyre(t: str | None) -> str:
    if not t:
        return "unknown"
    t = t.lower()
    for c in TYRE_COMPOUNDS:
        if c in t:
            return c
    return "unknown"


def _norm_weather(w: str | None) -> str:
    if not w:
        return "unknown"
    w = w.lower()
    for wt in WEATHER_TYPES:
        if wt in w:
            return wt
    return "unknown"


def _lap_phase(lap: int | None, total_laps: int | None) -> str:
    """Divide race into thirds: early / mid / late."""
    if lap is None or total_laps is None or total_laps == 0:
        return "unknown"
    frac = lap / total_laps
    if frac <= 1 / 3:
        return "early"
    if frac <= 2 / 3:
        return "mid"
    return "late"


def _outcome_to_class(outcome: str | None) -> str | None:
    """Map raw outcome string to one of the 7 penalty classes."""
    if outcome is None:
        return None
    o = outcome.lower()
    if "no further" in o or "nfa" in o:
        return "NFA"
    if "reprimand" in o:
        return "REP"
    if "5" in o and "second" in o:
        return "5s"
    if "10" in o and "second" in o:
        return "10s"
    if "drive-through" in o or "drive through" in o:
        return "DT"
    if "grid" in o:
        return "GRID"
    if "disqualif" in o:
        return "DSQ"
    # Generic time penalty — map by duration
    import re
    m = re.search(r"(\d+)s?\s+time\s+penalty", o)
    if m:
        secs = int(m.group(1))
        if secs <= 5:
            return "5s"
        if secs <= 10:
            return "10s"
        return "GRID"
    return None


# ---------------------------------------------------------------------------
# Main feature extractor
# ---------------------------------------------------------------------------

def extract_features(record: dict[str, Any]) -> dict[str, Any]:
    """
    Extract a flat feature dict from an enriched incident record.

    Expected record keys (all optional, defaults to safe fallbacks):
      From decision_parser:
        infraction_type, outcome, session_type, lap_number, penalty_points,
        car_number, driver_name
      From OpenF1 linker:
        openf1.weather_data, openf1.laps (tyre compound)
      From FastF1 slicer:
        telemetry.speed_diff, telemetry.braking_delta, telemetry.overlap_s
      Extra context:
        total_laps, corner_type, article_cited, position_change,
        safety_car_out, driver_history.penalty_points_ytd,
        driver_history.repeat_infraction
    """
    parser_data = record.get("parsed", record)
    openf1 = record.get("openf1") or {}
    telemetry = record.get("telemetry_features") or {}
    driver_hist = record.get("driver_history") or {}

    # --- infraction context ---
    infraction_type = parser_data.get("infraction_type") or "unknown"
    session_raw = parser_data.get("session_type")
    session_type = _norm_session(session_raw)
    lap_number = parser_data.get("lap_number")
    total_laps = record.get("total_laps")
    lap_phase = _lap_phase(lap_number, total_laps)
    article_cited = record.get("article_cited") or "unknown"
    corner_type = record.get("corner_type") or "unknown"

    # --- driving dynamics from telemetry ---
    speed_diff = telemetry.get("speed_diff_kph", 0.0) or 0.0
    braking_delta = telemetry.get("braking_point_delta_m", 0.0) or 0.0
    overlap_s = telemetry.get("overlap_s", 0.0) or 0.0
    drs_deployed = int(bool(telemetry.get("drs_deployed", False)))

    # --- race context ---
    position_change = record.get("position_change", 0) or 0
    safety_car_out = int(bool(record.get("safety_car_out", False)))
    vsc_out = int(bool(record.get("vsc_out", False)))

    # weather from OpenF1 weather_data
    weather_data = openf1.get("weather_data") or {}
    rainfall = int(bool(weather_data.get("rainfall", False)))
    weather = "wet" if rainfall else "dry"

    # tyre compound from OpenF1 laps data
    laps_data = openf1.get("laps") or []
    tyre = "unknown"
    if laps_data:
        tyre = _norm_tyre(laps_data[0].get("compound"))

    # --- driver history ---
    penalty_points_ytd = driver_hist.get("penalty_points_ytd", 0) or 0
    repeat_infraction = int(bool(driver_hist.get("repeat_infraction", False)))

    # --- label ---
    outcome_raw = parser_data.get("outcome")
    penalty_class = _outcome_to_class(outcome_raw)
    penalty_class_idx = PENALTY_CLASS_TO_IDX.get(penalty_class, -1) if penalty_class else -1

    return {
        # identifiers
        "doc_id": record.get("doc_id"),
        "season": record.get("season"),
        "driver": parser_data.get("driver_name") or "unknown",
        "car_number": parser_data.get("car_number"),

        # infraction
        "infraction_type": infraction_type,
        "article_cited": article_cited,
        "session_type": session_type,
        "lap_phase": lap_phase,
        "corner_type": corner_type,

        # driving dynamics
        "speed_diff_kph": speed_diff,
        "braking_point_delta_m": braking_delta,
        "overlap_s": overlap_s,
        "drs_deployed": drs_deployed,

        # race context
        "position_change": position_change,
        "safety_car_out": safety_car_out,
        "vsc_out": vsc_out,
        "weather": weather,
        "tyre_compound": tyre,

        # history
        "penalty_points_ytd": penalty_points_ytd,
        "repeat_infraction": repeat_infraction,

        # target
        "penalty_class": penalty_class,
        "penalty_class_idx": penalty_class_idx,
        "penalty_points_delta": parser_data.get("penalty_points") or 0,
    }


def batch_extract_features(records: list[dict]) -> list[dict]:
    """Extract features from a list of enriched incident records."""
    return [extract_features(r) for r in records]
