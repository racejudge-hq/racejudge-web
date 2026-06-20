"""
Weather Linker — Phase 3.

Attaches OpenF1 weather context to incidents at the time of the incident.

OpenF1 /weather endpoint: returns 1-minute interval weather data per session.
  air_temp, track_temp, humidity, rainfall, wind_speed, wind_direction, pressure

Usage:
    linker = WeatherLinker()
    context = linker.get_weather_at_incident(session_key=9158, incident_time=dt)
    # context = {air_temp, track_temp, humidity, rainfall, wind_speed}

    await linker.backfill_session(session_key=9158, db=db)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

log = logging.getLogger(__name__)


def _parse_dt(s: str) -> datetime:
    # OpenF1 timestamps may carry a +00:00 offset or trailing 'Z' — fromisoformat
    # handles offsets and fractional seconds; strptime did not.
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


class WeatherLinker:

    def __init__(self):
        from packages.pipeline.linkers.openf1_client import OpenF1Client
        self._client = OpenF1Client()
        self._cache: dict[int, list[dict]] = {}  # session_key → weather rows

    def _get_weather(self, session_key: int) -> list[dict]:
        if session_key not in self._cache:
            self._cache[session_key] = self._client.weather(session_key=session_key)
        return self._cache[session_key]

    def get_weather_at_incident(
        self,
        session_key: int,
        incident_time: datetime | str | None,
    ) -> dict | None:
        """
        Return the closest weather snapshot to the incident timestamp.
        Returns None if weather data unavailable or session_key unknown.
        """
        weather_rows = self._get_weather(session_key)
        if not weather_rows or incident_time is None:
            return None

        if isinstance(incident_time, str):
            try:
                incident_time = _parse_dt(incident_time)
            except Exception:
                return None

        # Find closest by timestamp
        best: dict | None = None
        best_delta: float = float("inf")
        for row in weather_rows:
            date_str = row.get("date")
            if not date_str:
                continue
            try:
                row_dt = _parse_dt(date_str)
                delta  = abs((row_dt - incident_time).total_seconds())
                if delta < best_delta:
                    best_delta = delta
                    best = row
            except Exception:
                continue

        if best is None:
            return None

        return {
            "air_temp":        best.get("air_temperature"),
            "track_temp":      best.get("track_temperature"),
            "humidity":        best.get("humidity"),
            "rainfall":        bool(best.get("rainfall", False)),
            "wind_speed":      best.get("wind_speed"),
            "wind_direction":  best.get("wind_direction"),
            "pressure":        best.get("pressure"),
            "timestamp_delta_s": round(best_delta, 1),
        }

    async def backfill_session(self, session_key: int, db) -> int:
        """
        Attach weather context to all incidents in a session that have
        an estimated incident time but no weather_context yet.

        Returns count of incidents updated.
        """
        from sqlalchemy import select

        from packages.db.models import Decision, Incident, RaceControlMessage

        # Get incidents for session without weather context
        result = await db.execute(
            select(Incident)
            .where(
                Incident.session_key == session_key,
                Incident.weather_context.is_(None),
            )
        )
        incidents = result.scalars().all()
        if not incidents:
            return 0

        updated = 0
        for incident in incidents:
            # Use earliest linked RC message time as incident time
            rc_result = await db.execute(
                select(RaceControlMessage.date)
                .where(RaceControlMessage.incident_id == incident.incident_id)
                .order_by(RaceControlMessage.date)
                .limit(1)
            )
            rc_row = rc_result.first()

            if rc_row and rc_row[0]:
                incident_time = rc_row[0]
            else:
                # Fall back to decision published_at
                dec_result = await db.execute(
                    select(Decision.published_at)
                    .where(Decision.doc_id == incident.doc_id)
                )
                dec_row = dec_result.first()
                incident_time = dec_row[0] if dec_row else None

            if incident_time is None:
                continue

            ctx = self.get_weather_at_incident(session_key, incident_time)
            if ctx:
                incident.weather_context = ctx
                updated += 1

        if updated > 0:
            await db.flush()
            log.info("Updated weather context for %d incidents in session %d",
                     updated, session_key)

        return updated
