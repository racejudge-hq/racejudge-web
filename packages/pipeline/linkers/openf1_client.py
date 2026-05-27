"""
OpenF1 API client — Phase 3.

Fetches race_control messages, team_radio recordings, and lap data
from the public OpenF1 API (openf1.org).  All endpoints are public
and require no authentication.

Rate limiting: OpenF1 has no published rate limit but we apply a
1-second delay between requests as good citizenship.

Usage:
    from packages.pipeline.linkers.openf1_client import OpenF1Client
    client = OpenF1Client()
    messages = client.race_control(session_key=9165)
    radio = client.team_radio(session_key=9165, driver_number=44)
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

OPENF1_BASE = "https://api.openf1.org/v1"
REQUEST_DELAY = 1.0  # seconds between API calls

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "RaceJudge-Linker/1.0 (+https://github.com/racejudge-hq/racejudge)",
    "Accept": "application/json",
}


class OpenF1Client:
    def __init__(self, base_url: str = OPENF1_BASE, delay: float = REQUEST_DELAY):
        self._base = base_url.rstrip("/")
        self._delay = delay
        self._last_request: float = 0.0

    def _get(self, path: str, **params: Any) -> list[dict]:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self._delay:
            time.sleep(self._delay - elapsed)

        url = f"{self._base}/{path.lstrip('/')}"
        resp = requests.get(url, params={k: v for k, v in params.items() if v is not None},
                            headers=HEADERS, timeout=30)
        self._last_request = time.monotonic()
        resp.raise_for_status()
        return resp.json()

    # ── Sessions ────────────────────────────────────────────────────────────

    def sessions(
        self,
        *,
        year: int | None = None,
        circuit_short_name: str | None = None,
        session_name: str | None = None,  # "Race", "Qualifying", "Sprint"
    ) -> list[dict]:
        """Return session metadata. Returns a list of session objects."""
        return self._get("sessions", year=year, circuit_short_name=circuit_short_name,
                         session_name=session_name)

    def session_key_for_gp(self, year: int, circuit_short_name: str, session_name: str = "Race") -> int | None:
        """Convenience: look up a session_key by GP + session type."""
        sessions = self.sessions(year=year, circuit_short_name=circuit_short_name,
                                 session_name=session_name)
        return sessions[0]["session_key"] if sessions else None

    # ── Race control ─────────────────────────────────────────────────────────

    def race_control(
        self,
        *,
        session_key: int,
        category: str | None = None,   # "Flag", "SafetyCar", "Drs", etc.
    ) -> list[dict]:
        """
        Fetch race control messages for a session.
        Returns messages sorted chronologically (OpenF1 returns them sorted).
        """
        return self._get("race_control", session_key=session_key, category=category)

    # ── Team radio ───────────────────────────────────────────────────────────

    def team_radio(
        self,
        *,
        session_key: int,
        driver_number: int | None = None,
    ) -> list[dict]:
        """
        Fetch team radio recording metadata for a session.
        Each record has a `recording_url` (already-public FOM broadcast feed URL).
        """
        return self._get("team_radio", session_key=session_key, driver_number=driver_number)

    # ── Laps ─────────────────────────────────────────────────────────────────

    def laps(
        self,
        *,
        session_key: int,
        driver_number: int | None = None,
        lap_number: int | None = None,
    ) -> list[dict]:
        return self._get("laps", session_key=session_key, driver_number=driver_number,
                         lap_number=lap_number)

    # ── Drivers ──────────────────────────────────────────────────────────────

    def drivers(self, *, session_key: int) -> list[dict]:
        return self._get("drivers", session_key=session_key)

    def driver_number_for_name(self, session_key: int, name_fragment: str) -> int | None:
        """Find a driver's number by partial name match (case-insensitive)."""
        drivers = self.drivers(session_key=session_key)
        name_lower = name_fragment.lower()
        for d in drivers:
            full = d.get("full_name", "") or ""
            last = d.get("last_name", "") or ""
            if name_lower in full.lower() or name_lower in last.lower():
                return d.get("driver_number")
        return None
