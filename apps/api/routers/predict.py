"""
Penalty prediction API endpoint — Phase 5.

Returns probability distribution over 7 penalty classes for a given incident.
Model gated behind feature flag: ENABLE_PREDICTIONS env var must be "true".

When model is not available, returns a 503 with clear guidance.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)
router = APIRouter(tags=["predict"])

PENALTY_CLASSES = ["NFA", "REP", "5s", "10s", "DT", "GRID", "DSQ"]


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class IncidentInput(BaseModel):
    """Incident fields for penalty prediction. All fields optional — model uses defaults."""
    infraction_type: str | None = None
    session_type: str | None = None
    lap_number: int | None = None
    total_laps: int | None = None
    article_cited: str | None = None
    corner_type: str | None = None
    speed_diff_kph: float = 0.0
    braking_point_delta_m: float = 0.0
    overlap_s: float = 0.0
    drs_deployed: bool = False
    position_change: int = 0
    safety_car_out: bool = False
    vsc_out: bool = False
    weather: str | None = None
    tyre_compound: str | None = None
    penalty_points_ytd: int = 0
    repeat_infraction: bool = False
    season: int | None = None


class PredictionResult(BaseModel):
    predicted_class: str = Field(description="Most likely penalty class")
    confidence: float = Field(description="Probability of predicted class (0–1)")
    proba: dict[str, float] = Field(description="Probability distribution over all 7 classes")
    model_version: str
    disclaimer: str = Field(
        default="This is a probabilistic model output for research purposes only. "
                "It does not represent an official FIA determination."
    )


# ---------------------------------------------------------------------------
# Model loading (lazy, cached)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _load_model():
    from pathlib import Path
    try:
        from packages.ml.predictor import PenaltyPredictor
        model_path = Path(__file__).resolve().parents[3] / "models" / "penalty_v1.pkl"
        if not model_path.exists():
            return None, "Model file not found — train with: python -m packages.ml.train"
        model = PenaltyPredictor.load(model_path)
        return model, None
    except ImportError as exc:
        return None, f"ML dependencies not installed: {exc}"
    except Exception as exc:
        log.error("Failed to load penalty model: %s", exc)
        return None, str(exc)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/predict", response_model=PredictionResult)
async def predict_penalty(incident: IncidentInput) -> dict[str, Any]:
    """
    Predict the most likely penalty outcome for an incident.

    Requires the penalty model to be trained (Phase 5).
    Set ENABLE_PREDICTIONS=true to activate this endpoint.
    """
    if os.environ.get("ENABLE_PREDICTIONS", "false").lower() != "true":
        raise HTTPException(
            status_code=503,
            detail="Penalty prediction not yet available. "
                   "Set ENABLE_PREDICTIONS=true once the Phase 5 model is trained.",
        )

    model, error = _load_model()
    if model is None:
        raise HTTPException(status_code=503, detail=error or "Model unavailable")

    # Build a record dict matching what extract_features expects
    record = {
        "season": incident.season,
        "total_laps": incident.total_laps,
        "article_cited": incident.article_cited,
        "corner_type": incident.corner_type,
        "position_change": incident.position_change,
        "safety_car_out": incident.safety_car_out,
        "vsc_out": incident.vsc_out,
        "parsed": {
            "infraction_type": incident.infraction_type,
            "session_type": incident.session_type,
            "lap_number": incident.lap_number,
            "outcome": None,
            "penalty_points": None,
        },
        "telemetry_features": {
            "speed_diff_kph": incident.speed_diff_kph,
            "braking_point_delta_m": incident.braking_point_delta_m,
            "overlap_s": incident.overlap_s,
            "drs_deployed": incident.drs_deployed,
        },
        "openf1": {
            "weather_data": {"rainfall": incident.weather == "wet"},
            "laps": [{"compound": incident.tyre_compound}] if incident.tyre_compound else [],
        },
        "driver_history": {
            "penalty_points_ytd": incident.penalty_points_ytd,
            "repeat_infraction": incident.repeat_infraction,
        },
    }

    try:
        result = model.predict(record)
    except Exception as exc:
        log.error("Prediction error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Prediction failed: {exc}")

    return {
        "predicted_class": result["predicted_class"],
        "confidence": result["confidence"],
        "proba": result["proba"],
        "model_version": "penalty-v1-xgb",
        "disclaimer": (
            "This is a probabilistic model output for research purposes only. "
            "It does not represent an official FIA determination."
        ),
    }
