"""
Decision → OpenF1 linker — Phase 3.

For each ingested decision, attempts to link it to:
  - Race control messages from the same session and approximate time window
  - Team radio recordings from the implicated driver

Input:  data/parsed/decisions.jsonl
Output: data/linked/decisions_linked.jsonl  (same schema + openf1 fields)

Usage:
    python -m packages.pipeline.linkers.decision_linker --season 2024
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path

from packages.pipeline.linkers.openf1_client import OpenF1Client

ROOT = Path(__file__).resolve().parents[3]
PARSED_JSONL  = ROOT / "data" / "parsed" / "decisions.jsonl"
LINKED_DIR    = ROOT / "data" / "linked"
LINKED_JSONL  = LINKED_DIR / "decisions_linked.jsonl"

LINKED_DIR.mkdir(parents=True, exist_ok=True)

# Map FIA GP name fragments → OpenF1 circuit_short_name
# Extend as needed; OpenF1 uses ICAO-style short names
GP_TO_CIRCUIT: dict[str, str] = {
    "abu dhabi":        "Yas Marina",
    "australian":       "Melbourne",
    "austrian":         "Spielberg",
    "azerbaijan":       "Baku",
    "bahrain":          "Sakhir",
    "belgian":          "Spa",
    "british":          "Silverstone",
    "canadian":         "Montreal",
    "chinese":          "Shanghai",
    "dutch":            "Zandvoort",
    "emilia romagna":   "Imola",
    "hungarian":        "Budapest",
    "italian":          "Monza",
    "japanese":         "Suzuka",
    "las vegas":        "Las Vegas",
    "mexico":           "Mexico City",
    "miami":            "Miami",
    "monaco":           "Monaco",
    "qatar":            "Lusail",
    "são paulo":        "Interlagos",
    "sao paulo":        "Interlagos",
    "saudi":            "Jeddah",
    "singapore":        "Marina Bay",
    "spanish":          "Barcelona",
    "united states":    "Austin",
}

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_car_number(title: str) -> int | None:
    m = re.search(r"car\s+(\d+)", title, re.IGNORECASE)
    return int(m.group(1)) if m else None


def _gp_to_circuit(title: str) -> str | None:
    title_lower = title.lower()
    for fragment, circuit in GP_TO_CIRCUIT.items():
        if fragment in title_lower:
            return circuit
    return None


def _session_type(title: str) -> str:
    title_lower = title.lower()
    if "sprint" in title_lower:
        return "Sprint"
    if "qualifying" in title_lower or "qualification" in title_lower:
        return "Qualifying"
    if "practice" in title_lower:
        return "Practice 1"
    return "Race"


# ---------------------------------------------------------------------------
# Linking
# ---------------------------------------------------------------------------

def link_decision(record: dict, client: OpenF1Client) -> dict:
    """
    Attempt to enrich a decision record with OpenF1 race_control + radio links.
    Returns the record with added `openf1` key (may be empty dict on failure).
    """
    enriched = {**record, "openf1": {}}
    title = record.get("title", "")
    season = record.get("season")
    car_number = _extract_car_number(title)
    circuit = _gp_to_circuit(title)

    if not circuit or not season:
        return enriched

    session_name = _session_type(title)
    session_key = client.session_key_for_gp(season, circuit, session_name)
    if not session_key:
        log.debug("No session found for %s %s %s", season, circuit, session_name)
        return enriched

    openf1: dict = {"session_key": session_key, "circuit": circuit}

    # Race control messages (all — consumer can filter by flag/drs/etc.)
    try:
        rc_messages = client.race_control(session_key=session_key)
        openf1["race_control_count"] = len(rc_messages)
        openf1["race_control_sample"] = rc_messages[:3]  # preview
    except Exception as exc:
        log.warning("race_control fetch failed for session %s: %s", session_key, exc)

    # Team radio for the implicated driver
    if car_number:
        try:
            radio = client.team_radio(session_key=session_key, driver_number=car_number)
            openf1["team_radio"] = [
                {"date": r.get("date"), "recording_url": r.get("recording_url")}
                for r in radio
            ]
        except Exception as exc:
            log.warning("team_radio fetch failed for session %s car %s: %s", session_key, car_number, exc)

    enriched["openf1"] = openf1
    return enriched


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def run(season: int | None = None) -> None:
    records = [json.loads(line) for line in PARSED_JSONL.read_text().splitlines() if line.strip()]
    if season:
        records = [r for r in records if r.get("season") == season]

    log.info("Linking %d decisions to OpenF1...", len(records))

    client = OpenF1Client()
    linked: list[dict] = []

    for i, rec in enumerate(records):
        log.info("[%d/%d] %s", i + 1, len(records), rec.get("title", "")[:60])
        linked.append(link_decision(rec, client))

    with LINKED_JSONL.open("w", encoding="utf-8") as f:
        for r in linked:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    log.info("Wrote %d linked records to %s", len(linked), LINKED_JSONL)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Link FIA decisions to OpenF1 data")
    parser.add_argument("--season", type=int)
    args = parser.parse_args()
    run(args.season)
