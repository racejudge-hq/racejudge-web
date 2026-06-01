"""
FastF1 telemetry slicer — Phase 3.

Fetches lap timing and car telemetry for a specific incident window
(±2 laps around the incident lap) using the FastF1 library.

Caches data locally in fastf1_cache/ (gitignored).
Requires internet access to FastF1's Ergast/OpenF1 backend on first fetch.

Usage:
    from packages.pipeline.telemetry.fastf1_slicer import TelemetrySlicer
    slicer = TelemetrySlicer()
    data = slicer.get_incident_telemetry(year=2024, gp="Silverstone",
                                          session="R", driver="HAM", lap=12)

Dependencies (uncomment in requirements.txt when starting Phase 3):
    fastf1>=3.3.0
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = ROOT / "fastf1_cache"
CACHE_DIR.mkdir(exist_ok=True)

log = logging.getLogger(__name__)


def _require_fastf1():
    try:
        import fastf1
        return fastf1
    except ImportError as exc:
        raise ImportError(
            "fastf1 not installed. Uncomment fastf1>=3.3.0 in requirements.txt "
            "and run: pip install -r requirements.txt"
        ) from exc


class TelemetrySlicer:
    """Fetches and slices FastF1 telemetry for a specific incident window."""

    def __init__(self, cache_dir: Path = CACHE_DIR):
        ff1 = _require_fastf1()
        ff1.Cache.enable_cache(str(cache_dir))
        self._ff1 = ff1

    def get_session(self, year: int, gp: str, session: str = "R"):
        """
        Load a FastF1 session.
        session: "R" (Race), "Q" (Qualifying), "S" (Sprint), "FP1/2/3"
        """
        sess = self._ff1.get_session(year, gp, session)
        sess.load()
        return sess

    def get_incident_telemetry(
        self,
        year: int,
        gp: str,
        driver: str,        # driver abbreviation e.g. "HAM", "VER"
        lap: int,
        session: str = "R",
        window_laps: int = 2,
    ) -> dict[str, Any]:
        """
        Returns telemetry and timing data for [lap-window, lap+window].
        Output dict keys:
          - laps: DataFrame of lap timing
          - telemetry: DataFrame of car telemetry (speed, throttle, brake, DRS, gear)
          - fastest_sector: dict with best sector times around the incident lap
        """
        sess = self.get_session(year, gp, session)
        driver_laps = sess.laps.pick_driver(driver)

        lap_min = max(1, lap - window_laps)
        lap_max = lap + window_laps
        window_laps_df = driver_laps[
            (driver_laps["LapNumber"] >= lap_min) &
            (driver_laps["LapNumber"] <= lap_max)
        ]

        if window_laps_df.empty:
            log.warning("No laps found for %s lap %d±%d at %s %d", driver, lap, window_laps, gp, year)
            return {"laps": None, "telemetry": None}

        # Get telemetry for the incident lap specifically
        try:
            incident_lap = driver_laps[driver_laps["LapNumber"] == lap].iloc[0]
            telemetry = incident_lap.get_car_data().add_distance()
        except (IndexError, Exception) as exc:
            log.warning("Could not get telemetry for %s lap %d: %s", driver, lap, exc)
            telemetry = None

        return {
            "year": year,
            "gp": gp,
            "session": session,
            "driver": driver,
            "incident_lap": lap,
            "lap_window": [lap_min, lap_max],
            "laps": window_laps_df.to_dict("records") if not window_laps_df.empty else [],
            "telemetry": telemetry.to_dict("records") if telemetry is not None else None,
        }

    def compare_drivers(
        self,
        year: int,
        gp: str,
        drivers: list[str],
        lap: int,
        session: str = "R",
    ) -> dict[str, Any]:
        """
        Compare telemetry between two drivers on the same lap —
        useful for collision/impeding analysis.
        """
        sess = self.get_session(year, gp, session)
        result = {}
        for driver in drivers:
            try:
                driver_laps = sess.laps.pick_driver(driver)
                incident_lap = driver_laps[driver_laps["LapNumber"] == lap].iloc[0]
                telemetry = incident_lap.get_car_data().add_distance()
                result[driver] = {
                    "lap_time": str(incident_lap["LapTime"]),
                    "telemetry": telemetry[["Distance", "Speed", "Throttle", "Brake", "DRS", "nGear"]].to_dict("records"),
                }
            except Exception as exc:
                log.warning("Could not get telemetry for %s lap %d: %s", driver, lap, exc)
                result[driver] = None  # type: ignore[assignment]
        return result
