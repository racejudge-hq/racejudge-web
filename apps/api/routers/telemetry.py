"""
Telemetry API — Phase 3.

Exposes FastF1 incident telemetry over HTTP so the Next.js frontend
can render speed/throttle/brake traces without bundling FastF1.

Endpoints:
  GET /v1/telemetry/incident  — single driver telemetry window
  GET /v1/telemetry/compare   — two-driver comparison for collision analysis

FastF1 data is cached in fastf1_cache/ on first request; subsequent
calls for the same session serve from disk.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

log = logging.getLogger(__name__)
router = APIRouter(tags=["telemetry"])


class TelemetryResponse(BaseModel):
    year: int
    gp: str
    session: str
    driver: str
    incident_lap: int
    lap_window: list[int]
    laps: list[dict] | None
    telemetry: list[dict] | None


class CompareResponse(BaseModel):
    year: int
    gp: str
    session: str
    lap: int
    drivers: dict[str, Any]


def _get_slicer():
    try:
        from packages.pipeline.telemetry.fastf1_slicer import TelemetrySlicer
        return TelemetrySlicer()
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"FastF1 not available: {exc}. Install fastf1>=3.3.0.",
        ) from exc
    except Exception as exc:
        log.error("TelemetrySlicer init error: %s", exc)
        raise HTTPException(status_code=503, detail=f"Telemetry service unavailable: {exc}") from exc


@router.get("/telemetry/incident", response_model=TelemetryResponse)
async def get_incident_telemetry(
    year: Annotated[int, Query(ge=2018, le=2030, description="Season year")],
    gp: Annotated[str, Query(min_length=2, description="GP name e.g. 'Silverstone'")],
    driver: Annotated[str, Query(min_length=2, max_length=3, description="Driver abbreviation e.g. HAM")],
    lap: Annotated[int, Query(ge=1, le=100, description="Incident lap number")],
    session: Annotated[str, Query(description="Session type: R, Q, S, FP1, FP2, FP3")] = "R",
    window: Annotated[int, Query(ge=1, le=5, description="Laps either side of incident")] = 2,
) -> dict:
    """
    Fetch car telemetry (speed, throttle, brake, DRS, gear) for a ±window lap
    window around the incident lap for a specific driver.
    """
    slicer = _get_slicer()
    try:
        data = slicer.get_incident_telemetry(
            year=year,
            gp=gp,
            driver=driver.upper(),
            lap=lap,
            session=session.upper(),
            window_laps=window,
        )
    except Exception as exc:
        log.error("Telemetry fetch error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if data.get("laps") is None:
        raise HTTPException(
            status_code=404,
            detail=f"No data found for {driver} lap {lap} at {gp} {year}",
        )
    return data


@router.get("/telemetry/compare", response_model=CompareResponse)
async def compare_driver_telemetry(
    year: Annotated[int, Query(ge=2018, le=2030)],
    gp: Annotated[str, Query(min_length=2)],
    drivers: Annotated[str, Query(description="Comma-separated driver abbreviations e.g. HAM,VER")],
    lap: Annotated[int, Query(ge=1, le=100)],
    session: Annotated[str, Query()] = "R",
) -> dict:
    """
    Compare telemetry between two+ drivers on the same lap.
    Useful for collision / impeding analysis.
    """
    driver_list = [d.strip().upper() for d in drivers.split(",") if d.strip()]
    if len(driver_list) < 2:
        raise HTTPException(status_code=422, detail="Provide at least 2 comma-separated drivers")
    if len(driver_list) > 4:
        raise HTTPException(status_code=422, detail="Maximum 4 drivers per comparison")

    slicer = _get_slicer()
    try:
        comparison = slicer.compare_drivers(
            year=year,
            gp=gp,
            drivers=driver_list,
            lap=lap,
            session=session.upper(),
        )
    except Exception as exc:
        log.error("Comparison error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "year": year,
        "gp": gp,
        "session": session.upper(),
        "lap": lap,
        "drivers": comparison,
    }
