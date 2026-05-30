"""
Live session ingestion flow — Phase 3.

Polls OpenF1 for new race control messages during a live session,
detects incidents, fetches telemetry + radio clips, and stores results.

Designed to run every 60 seconds during a race session.
The Prefect work pool "live-session" should be configured with
min_workers=1 during race weekends.

Usage:
    # Start monitoring a live session:
    from packages.pipeline.flows.live_session_flow import live_session_flow
    live_session_flow(session_key=9158)

    # Or via CLI:
    python -m packages.pipeline.flows.live_session_flow --session-key 9158
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

# Graceful stub if Prefect not installed
try:
    from prefect import flow, task, get_run_logger
    from prefect.tasks import task_input_hash
    HAS_PREFECT = True
except ImportError:
    HAS_PREFECT = False

    def flow(fn=None, **kwargs):
        return fn if fn else lambda f: f

    def task(fn=None, **kwargs):
        return fn if fn else lambda f: f

    def get_run_logger():
        return logging.getLogger("prefect.stub")

    def task_input_hash(*args, **kwargs):
        return None


# Race control message types that indicate a stewards' incident
INCIDENT_MESSAGE_TYPES = {
    "SafetyCar",
    "VirtualSafetyCar",
    "Flag",
    "Incident",
    "Investigation",
    "Penalty",
    "BlackAndWhiteFlag",
}

INCIDENT_FLAG_NOTES = {
    "BLUE FLAG",
    "BLACK FLAG",
    "BLACK AND WHITE FLAG",
    "INCIDENT NOTED",
    "UNDER INVESTIGATION",
    "NOTED - ALLEGED BREACH",
}


def _is_incident_message(msg: dict) -> bool:
    """Return True if a race control message relates to a stewards' incident."""
    category = (msg.get("category") or "").upper()
    message = (msg.get("message") or "").upper()
    flag = (msg.get("flag") or "").upper()

    if category == "FLAG" and flag in {"BLACK", "BLACK AND WHITE"}:
        return True
    if category == "INCIDENT":
        return True
    if any(note in message for note in INCIDENT_FLAG_NOTES):
        return True
    return False


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@task(name="fetch-race-control", retries=3, retry_delay_seconds=10)
def fetch_race_control_task(session_key: int, after: str | None = None) -> list[dict]:
    """Fetch new race control messages since `after` timestamp."""
    from packages.pipeline.linkers.openf1_client import OpenF1Client
    client = OpenF1Client()
    messages = client.race_control(session_key=session_key)
    if after:
        messages = [m for m in messages if (m.get("date") or "") > after]
    return messages


@task(name="detect-incidents")
def detect_incidents_task(messages: list[dict]) -> list[dict]:
    """Filter race control messages to just incident-related ones."""
    return [m for m in messages if _is_incident_message(m)]


@task(name="fetch-incident-telemetry", retries=2, retry_delay_seconds=30)
def fetch_telemetry_task(
    session_key: int,
    driver_number: int,
    incident_date: str,
) -> dict[str, Any] | None:
    """Fetch FastF1 telemetry for a driver around an incident time."""
    try:
        from packages.pipeline.linkers.openf1_client import OpenF1Client
        client = OpenF1Client()

        # Get the lap number from OpenF1 laps
        laps = client.laps(session_key=session_key, driver_number=driver_number)
        if not laps:
            return None

        # Find the lap that contains the incident time
        incident_dt = incident_date[:19]  # truncate to seconds
        lap_num = None
        for lap in laps:
            lap_start = (lap.get("date_start") or "")[:19]
            if lap_start <= incident_dt:
                lap_num = lap.get("lap_number")

        if lap_num is None:
            return {"session_key": session_key, "driver_number": driver_number, "lap": None}

        return {
            "session_key": session_key,
            "driver_number": driver_number,
            "lap_number": lap_num,
            "lap_data": lap,
        }
    except Exception as exc:
        log.warning("Telemetry fetch failed for driver %d: %s", driver_number, exc)
        return None


@task(name="fetch-incident-radio", retries=2, retry_delay_seconds=15)
def fetch_radio_task(
    session_key: int,
    driver_number: int,
    incident_date: str,
    window_seconds: int = 60,
) -> list[dict]:
    """Fetch team radio clips around an incident."""
    try:
        from packages.pipeline.audio.radio_fetcher import RadioFetcher
        fetcher = RadioFetcher()
        return fetcher.fetch_incident_clips(
            session_key=session_key,
            driver_number=driver_number,
            incident_time=incident_date,
            window_seconds=window_seconds,
            max_clips=3,
        )
    except Exception as exc:
        log.warning("Radio fetch failed for driver %d: %s", driver_number, exc)
        return []


@task(name="store-incident")
def store_incident_task(incident_data: dict) -> str:
    """
    Persist incident data to the database or a local JSONL file.
    Phase 3: writes to live_incidents.jsonl
    Phase 4+: upserts to incidents table
    """
    import json
    from pathlib import Path

    output_path = Path(__file__).resolve().parents[3] / "data" / "live_incidents.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        **incident_data,
        "stored_at": datetime.now(timezone.utc).isoformat(),
    }

    with open(output_path, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    incident_id = incident_data.get("message", {}).get("date", "unknown")
    log.info("Stored incident: %s", incident_id)
    return incident_id


# ---------------------------------------------------------------------------
# Flow
# ---------------------------------------------------------------------------

@flow(name="live-session-monitor", log_prints=True)
def live_session_flow(
    session_key: int,
    poll_interval_s: int = 60,
    max_polls: int = 200,  # ~3.3h of race coverage
) -> dict[str, Any]:
    """
    Monitor an active F1 session for incidents.
    Runs for up to max_polls iterations, sleeping poll_interval_s between each.

    In production this is triggered by the session_key when a session goes live.
    """
    import time

    logger = get_run_logger() if HAS_PREFECT else log
    logger.info("Starting live session monitor for session_key=%d", session_key)

    last_message_date: str | None = None
    total_incidents = 0
    polls = 0

    while polls < max_polls:
        polls += 1
        logger.info("Poll %d/%d for session %d", polls, max_polls, session_key)

        # Fetch new race control messages
        messages = fetch_race_control_task(session_key, after=last_message_date)

        if messages:
            last_message_date = max(m.get("date", "") for m in messages)

        # Detect incidents in this batch
        incidents = detect_incidents_task(messages)
        logger.info("Found %d incident messages in batch", len(incidents))

        for msg in incidents:
            total_incidents += 1
            driver_number = msg.get("driver_number") or msg.get("racing_number")
            incident_date = msg.get("date")

            telemetry = None
            radio_clips: list[dict] = []

            if driver_number and incident_date:
                telemetry = fetch_telemetry_task(session_key, driver_number, incident_date)
                radio_clips = fetch_radio_task(session_key, driver_number, incident_date)

            incident_data = {
                "session_key": session_key,
                "message": msg,
                "telemetry": telemetry,
                "radio_clips": radio_clips,
            }
            store_incident_task(incident_data)

        if not HAS_PREFECT:
            time.sleep(poll_interval_s)

    logger.info(
        "Live session monitor complete. session=%d, polls=%d, incidents=%d",
        session_key, polls, total_incidents,
    )
    return {"session_key": session_key, "polls": polls, "total_incidents": total_incidents}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Monitor a live F1 session")
    parser.add_argument("--session-key", type=int, required=True)
    parser.add_argument("--poll-interval", type=int, default=60)
    parser.add_argument("--max-polls", type=int, default=200)
    args = parser.parse_args()

    live_session_flow(
        session_key=args.session_key,
        poll_interval_s=args.poll_interval,
        max_polls=args.max_polls,
    )
