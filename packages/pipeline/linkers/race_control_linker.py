"""
Race Control Linker — Phase 3.

For every incident in the incidents table, finds and links the matching
OpenF1 race_control messages.

A message belongs to an incident when all of these hold:

  1. Same session.
  2. The message names one of the cars the decision was issued against —
     read out of the message text, not merely "the driver code appears
     somewhere", which matched HAM inside other words and matched a car
     number against a lap time.
  3. It falls inside the window around the time the decision states the
     incident happened. Race control notes an incident after it happens, so
     the window is asymmetric: measured on the 393 message/incident pairs
     that independently agree on both car and turn, the median message is
     264s after the incident and the p90 is 847s. Where the message names
     the same offence the decision was issued for, the window runs to half
     an hour instead — the stewards' own announcement lands that late, and
     the offence agreement is what identifies it.
  4. If both the message and the decision name a turn, they agree exactly.
     One turn of tolerance was measured and rejected: adjacent corners
     seconds apart are routinely separate incidents involving the same car
     and different opponents.
  5. A deleted lap time records only the offence it names: "TIME DELETED -
     TRACK LIMITS" is never the record of a collision ruling that happened
     to be minutes away.

Where the decision does not state a time (2019–22 mostly, plus documents
that print none), rule 3 is replaced by requiring the message to name the
same offence the decision was issued for. The wording alone is not enough:
a deleted-lap-times document covering eighteen drivers otherwise collects
every "NOTED" message any of them appear in.

Race control only names some offences. Where the decision's category is one
it never prints — a safety car line time, parc fermé, 107% — there is
nothing to agree with, and investigation wording is all that is left.

Links are written to `incident_race_control`. One message can belong to
several decisions: the stewards issue one per driver, so a message about an
incident between two cars is the record behind two of them.

Usage:
    linker = RaceControlLinker()
    await linker.link_session(session_key=9158, db=db)
    await linker.link_incident(incident_id="...", db=db)
"""

from __future__ import annotations

import logging
import re
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

# Race control writes after the fact. Negative tolerance is small — it only
# absorbs the minute the decision rounds its time to — while the positive side
# has to cover the stewards noting, investigating and announcing.
WINDOW_BEFORE_S = 120
WINDOW_AFTER_S  = 900

# The stewards' own announcement — "WILL BE INVESTIGATED", "5 SECOND TIME
# PENALTY FOR CAR n" — lands well past the p90 of the noting message, up to
# half an hour later. Reaching that far on time alone would sweep in unrelated
# messages, so the longer window is only offered when the message names the
# same offence the decision was issued for: the agreement does the
# identifying, and the clock is only confirming it is the same session moment.
WINDOW_AFTER_AGREED_S = 1800

# "CAR 44 (HAM)", "CARS 44 (HAM) AND 55 (SAI)", "CAR NO.16"
_CAR_RE  = re.compile(r"\bCARS?\s+(?:NO\.?\s*)?(\d{1,2})\b")
_ALSO_RE = re.compile(r"\bAND\s+(\d{1,2})\s*\(")
_TURN_RE = re.compile(r"\bTURN\s+(\d{1,2})\b")

# "CAR 4 (NOR) TIME 1:29.472 DELETED", "CAR 6 (HAD) LAP DELETED" — the lap
# time sits between the two words, so they are not adjacent.
_DELETED_RE = re.compile(r"\b(?:TIME|LAP)\s+(?:\d+:\d{2}\.\d+\s+)?DELETED\b")

# The offences race control prints, in the extractor's own vocabulary. Order
# matters: "VIRTUAL SAFETY CAR" has to be read before "SAFETY CAR".
OFFENCE_PHRASES: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern), category) for pattern, category in (
        (r"TRACK LIMITS|LEAVING THE TRACK AND GAINING",  "track_limits"),
        (r"DOUBLE YELLOW|YELLOW FLAG INFRINGEMENT",      "yellow_flag"),
        (r"CAUSING A COLLISION",                         "collision"),
        (r"FORCING ANOTHER DRIVER OFF THE TRACK",        "forcing_off_track"),
        (r"UNSAFE RELEASE",                              "unsafe_release"),
        (r"IMPEDING",                                    "impeding"),
        (r"SPEEDING IN THE PIT LANE",                    "pit_lane_speed"),
        (r"PIT LANE INFRINGEMENT",                       "pit_lane"),
        (r"VSC INFRINGEMENT|VIRTUAL SAFETY CAR",         "vsc"),
        (r"SAFETY CAR INFRINGEMENT",                     "safety_car"),
        (r"PRACTICE START",                              "practice_start"),
        (r"STARTING PROCEDURE INFRINGEMENT",             "start_procedure"),
        (r"FALSE START|MOVING BEFORE (?:THE )?SIGNAL",   "false_start"),
        (r"DRIVING ERRATICALLY|MOVING UNDER BRAKING",    "erratic_driving"),
        (r"DRIVING UNNECESSARILY SLOWLY",                "driving_slowly"),
        (r"CROSSING THE TRACK",                          "crossing_track"),
        (r"FAILING TO FOLLOW RACE DIRECTOR",             "race_director_instructions"),
    )
)

# The categories race control has words for. A decision outside this set —
# parc fermé, 107%, a technical non-compliance — is never going to be matched
# by offence, so it is not held to one.
SPOKEN_CATEGORIES = frozenset(category for _p, category in OFFENCE_PHRASES)


def _parse_dt(s: str) -> datetime:
    # OpenF1 timestamps may carry a +00:00 offset or trailing 'Z' plus optional
    # fractional seconds — fromisoformat handles all of them.
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _is_investigation_message(msg: str | None) -> bool:
    lower = (msg or "").lower()
    return any(kw in lower for kw in INVESTIGATION_KEYWORDS)


def cars_named(message: str | None, driver_number: int | None = None) -> set[int]:
    """The car numbers a race control message is about."""
    upper = (message or "").upper()
    cars = {int(n) for n in _CAR_RE.findall(upper)}
    cars |= {int(n) for n in _ALSO_RE.findall(upper)}
    if driver_number is not None:
        cars.add(driver_number)
    return cars


def turn_named(message: str | None) -> str | None:
    """The turn a race control message is about, as the corner column stores it."""
    match = _TURN_RE.search((message or "").upper())
    return match.group(1) if match else None


def offence_named(message: str | None) -> str | None:
    """The offence a race control message states, in the extractor's vocabulary."""
    upper = (message or "").upper()
    for pattern, category in OFFENCE_PHRASES:
        if pattern.search(upper):
            return category
    return None


def message_matches_incident(
    *,
    message: str | None,
    message_date: datetime | None,
    driver_number: int | None,
    car_numbers: set[int],
    incident_time: datetime | None,
    corner: str | None,
    infraction_category: str | None = None,
) -> bool:
    """Whether one race control message belongs to one incident.

    The caller has already established that both are in the same session.
    """
    if not car_numbers:
        return False

    cars = cars_named(message, driver_number)
    if not cars or not (cars & car_numbers):
        return False

    # The turn is held to exactly. Tolerating a neighbouring corner was tried
    # and reverted: car 11 at Mexico 2024 has two incidents 44 seconds apart,
    # turn 5 with car 30 and turn 4 with car 18, and one turn of slack linked
    # the turn 5 message to the turn 4 ruling.
    turn = turn_named(message)
    if turn is not None and corner is not None and turn != str(corner).strip():
        return False

    offence = offence_named(message)
    binding = infraction_category in SPOKEN_CATEGORIES
    agrees  = binding and offence == infraction_category

    # A deleted lap time is the record of the offence it names and no other.
    # Deletions are the most numerous message there is, so without this one
    # lands inside the window of nearly every ruling against a busy driver.
    if _DELETED_RE.search((message or "").upper()) and binding and not agrees:
        return False

    if incident_time is None:
        # Nothing to anchor on, so the offence has to carry it. Wording alone
        # let a deleted-lap-times document collect every message naming any of
        # its eighteen drivers — starting procedure, pit lane, collisions.
        if binding:
            return agrees
        return _is_investigation_message(message)

    if message_date is None:
        return False
    delta = (message_date - incident_time).total_seconds()
    after = WINDOW_AFTER_AGREED_S if agrees else WINDOW_AFTER_S
    return -WINDOW_BEFORE_S <= delta <= after


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

        # Already-stored messages, keyed on (when, what). The key has to be
        # built from parsed datetimes on both sides: the stored value renders
        # as "2024-05-26 14:30:00+00:00" and OpenF1 sends
        # "2024-05-26T14:30:00+00:00", so comparing the strings matched nothing
        # and every re-run re-inserted the whole session.
        existing = await db.execute(
            select(RaceControlMessage.date, RaceControlMessage.message)
            .where(RaceControlMessage.session_key == session_key)
        )
        existing_set: set[tuple[datetime | None, str | None]] = {
            (r.date, r.message) for r in existing.all()
        }

        inserted = 0
        for msg in raw_messages:
            date_str = msg.get("date", "")
            message  = msg.get("message", "")
            when     = _parse_dt(date_str) if date_str else datetime.now(tz=UTC)

            if (when, message) in existing_set:
                continue
            # Guard against the same message appearing twice in one response.
            existing_set.add((when, message))

            rc = RaceControlMessage(
                session_key   = session_key,
                date          = when,
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
        from sqlalchemy.orm import selectinload

        from packages.db.models import Incident, RaceControlMessage

        # The link collection is read below, so it has to be loaded here —
        # a lazy load on an async session raises rather than emitting SQL.
        inc_result = await db.execute(
            select(Incident)
            .options(selectinload(Incident.race_control_messages))
            .where(Incident.incident_id == incident_id)
        )
        incident = inc_result.scalar_one_or_none()
        if incident is None or not incident.session_key:
            log.debug("No session_key for incident %s — skipping RC link", incident_id)
            return 0

        # Every car the ruling was issued against, not just the first. A joint
        # summons names four, and a tabular ruling can name fifteen.
        car_numbers = {
            d.get("number") for d in (incident.drivers or [])
            if d.get("number") is not None
        }
        if not car_numbers:
            return 0

        rc_result = await db.execute(
            select(RaceControlMessage)
            .where(RaceControlMessage.session_key == incident.session_key)
        )
        messages = rc_result.scalars().all()

        # Load what is already linked so re-running is idempotent — messages are
        # shared between incidents, so "already has an incident" is not a
        # reason to skip one.
        existing = {rc.message_id for rc in incident.race_control_messages}

        linked = 0
        for rc in messages:
            if rc.message_id in existing:
                continue
            if message_matches_incident(
                message       = rc.message,
                message_date  = rc.date,
                driver_number = rc.driver_number,
                car_numbers   = car_numbers,
                incident_time = incident.incident_time,
                corner        = incident.corner,
                infraction_category = incident.infraction_category,
            ):
                incident.race_control_messages.append(rc)
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
