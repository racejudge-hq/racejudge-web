"""
Race Control Linker — Phase 3.

For every incident in the incidents table, finds and links the matching
OpenF1 race_control messages.

Matching strategy:
  1. Primary:  session_key + driver_number + timestamp window ±30s
  2. Secondary: session_key + message keyword match (driver code or car number)
  3. Tertiary:  session_key + "UNDER INVESTIGATION" near incident time

Writes incident_id FK to race_control_messages rows.
Also inserts new RC messages fetched from OpenF1 that don't exist yet.

Usage:
    linker = RaceControlLinker()
    await linker.link_session(session_key=9158, db=db)
    await linker.link_incident(incident_id="...", db=db)
"""

from __future__ import annotations

import contextlib
import logging
from datetime import UTC, datetime

log = logging.getLogger(__name__)

INVESTIGATION_KEYWORDS = [
    "under investigation",
    "noted",
    "penalty",
    "penalised",
    "reprimand",
    "disqualified",
    "excluded",
    "offence",
    "referred to",
]

WINDOW_SECONDS = 30  # ±30s around incident time


def _parse_dt(s: str) -> datetime:
    # OpenF1 timestamps may carry a +00:00 offset or trailing 'Z' plus optional
    # fractional seconds — fromisoformat handles all of them.
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _is_investigation_message(msg: str) -> bool:
    lower = msg.lower()
    return any(kw in lower for kw in INVESTIGATION_KEYWORDS)


def _driver_mentioned(msg: str, driver_code: str | None, car_number: int | None) -> bool:
    """Return True if the message mentions this driver by code or car number."""
    if driver_code and driver_code.upper() in msg.upper():
        return True
    if car_number is not None:
        patterns = [f"CAR {car_number}", f"#{car_number}", f"No.{car_number}",
                    f"No. {car_number}", f"CAR NO.{car_number}"]
        for p in patterns:
            if p in msg.upper():
                return True
    return False


class RaceControlLinker:

    def __init__(self):
        from packages.pipeline.linkers.openf1_client import OpenF1Client
        self._client = OpenF1Client()

    async def fetch_and_store_rc_messages(self, session_key: int, db) -> int:
        """
        Fetch all RC messages for a session from OpenF1 and insert new ones.
        Returns count of new messages inserted.
        """
        from sqlalchemy import select

        from packages.db.models import RaceControlMessage

        raw_messages = self._client.race_control(session_key=session_key)
        if not raw_messages:
            log.info("No race control messages for session %d", session_key)
            return 0

        # Get existing URLs to avoid duplicates (use date+message as dedup key)
        existing = await db.execute(
            select(RaceControlMessage.date, RaceControlMessage.message)
            .where(RaceControlMessage.session_key == session_key)
        )
        existing_set: set[str] = {
            f"{str(r.date)}:{r.message}" for r in existing.all()
        }

        inserted = 0
        for msg in raw_messages:
            date_str = msg.get("date", "")
            message  = msg.get("message", "")
            key      = f"{date_str}:{message}"

            if key in existing_set:
                continue

            rc = RaceControlMessage(
                session_key   = session_key,
                date          = _parse_dt(date_str) if date_str else datetime.now(tz=UTC),
                category      = msg.get("category"),
                message       = message,
                flag          = msg.get("flag"),
                scope         = msg.get("scope"),
                sector        = msg.get("sector"),
                driver_number = msg.get("driver_number"),
            )
            db.add(rc)
            inserted += 1

        if inserted > 0:
            await db.flush()
            log.info("Inserted %d new RC messages for session %d", inserted, session_key)

        return inserted

    async def link_incident(self, incident_id: str, db) -> int:
        """
        Link all matching RC messages to a single incident.
        Returns count of messages linked.
        """
        from sqlalchemy import select

        from packages.db.models import Decision, Incident, RaceControlMessage

        # Fetch incident + decision
        inc_result = await db.execute(
            select(Incident).where(Incident.incident_id == incident_id)
        )
        incident = inc_result.scalar_one_or_none()
        if incident is None or not incident.session_key:
            log.debug("No session_key for incident %s — skipping RC link", incident_id)
            return 0

        # Get driver info
        drivers   = incident.drivers or []
        car_num   = drivers[0].get("number") if drivers else None
        drv_code  = drivers[0].get("code") if drivers else None

        # Get decision published_at for time window
        dec_result = await db.execute(
            select(Decision).where(Decision.doc_id == incident.doc_id)
        )
        decision = dec_result.scalar_one_or_none()
        published_at = None
        if decision and decision.published_at:
            with contextlib.suppress(Exception):
                published_at = _parse_dt(decision.published_at)

        # Fetch unlinked RC messages for this session
        rc_result = await db.execute(
            select(RaceControlMessage)
            .where(
                RaceControlMessage.session_key == incident.session_key,
                RaceControlMessage.incident_id.is_(None),
            )
        )
        messages = rc_result.scalars().all()

        linked = 0
        for rc in messages:
            should_link = False

            # Strategy 1: time window
            if published_at and rc.date:
                delta = abs((rc.date - published_at).total_seconds())
                if delta <= WINDOW_SECONDS * 60:  # generous: 30 min window for decisions
                    should_link = True

            # Strategy 2: driver keyword match
            if not should_link and _is_investigation_message(rc.message) and _driver_mentioned(rc.message, drv_code, car_num):
                    should_link = True

            # Strategy 3: car number in driver_number field
            if not should_link and rc.driver_number is not None and car_num is not None and rc.driver_number == car_num:
                    should_link = True

            if should_link:
                rc.incident_id = incident_id
                linked += 1

        if linked > 0:
            await db.flush()
            log.info("Linked %d RC messages to incident %s", linked, incident_id)

        return linked

    async def link_session(self, session_key: int, db) -> dict:
        """
        Full pipeline for a session:
        1. Fetch + store RC messages from OpenF1
        2. Link to all unlinked incidents in this session

        Returns stats dict.
        """
        from sqlalchemy import select

        from packages.db.models import Incident

        new_rc = await self.fetch_and_store_rc_messages(session_key, db)

        # Get all incidents for this session
        result = await db.execute(
            select(Incident.incident_id)
            .where(Incident.session_key == session_key)
        )
        incident_ids = [row[0] for row in result.all()]

        total_linked = 0
        for inc_id in incident_ids:
            total_linked += await self.link_incident(inc_id, db)

        await db.commit()
        return {
            "session_key":   session_key,
            "new_rc_messages": new_rc,
            "incidents":     len(incident_ids),
            "rc_linked":     total_linked,
        }
