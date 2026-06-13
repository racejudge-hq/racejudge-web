"""
Driver Resolver — Phase 2.

Maps extracted driver names / car numbers to canonical driver records.

Sources (in priority order):
  1. Local cache (data/reference/drivers.json) — populated by seed_drivers.py
  2. Jolpica-F1 API (https://api.jolpi.ca/ergast/f1) — REST, no key required
  3. OpenF1 /drivers endpoint — session-scoped fallback

Handles:
  - Surname-only matches: "Hamilton" → {code:"HAM", full_name:"Lewis Hamilton"}
  - Abbreviation matches: "HAM", "VER", "NOR"
  - Car number matches: 44 → Hamilton, 1 → Verstappen
  - Name variants: "Max Verstappen" / "M. Verstappen" / "VERSTAPPEN"
  - Historical seasons: 2019–2025 driver rosters
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
import unicodedata
from pathlib import Path

log = logging.getLogger(__name__)

ROOT      = Path(__file__).resolve().parents[3]
CACHE_DIR = ROOT / "data" / "reference"
# read-only filesystem (serverless) — cache only used by pipeline
with contextlib.suppress(OSError):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
DRIVERS_CACHE = CACHE_DIR / "drivers.json"

# ---------------------------------------------------------------------------
# Driver record type
# ---------------------------------------------------------------------------

DriverRecord = dict  # {code, full_name, number, nationality, jolpica_id, seasons[]}

# Car #1 is worn by the reigning champion and changes hands; the Jolpica API
# only reports a driver's *current* permanent number, so the holder per season
# is curated here. Extend each January.
CHAMPION_NUMBER_BY_SEASON: dict[int, str] = {
    2022: "VER", 2023: "VER", 2024: "VER", 2025: "VER", 2026: "NOR",
}


# ---------------------------------------------------------------------------
# Known driver database (2019–2025) — updated from Jolpica-F1 by seed script
# ---------------------------------------------------------------------------

KNOWN_DRIVERS: list[DriverRecord] = [
    # 2025 grid
    {"code": "VER", "full_name": "Max Verstappen",        "number": 1,  "nationality": "Dutch"},
    {"code": "NOR", "full_name": "Lando Norris",          "number": 4,  "nationality": "British"},
    {"code": "LEC", "full_name": "Charles Leclerc",       "number": 16, "nationality": "Monégasque"},
    {"code": "PIA", "full_name": "Oscar Piastri",         "number": 81, "nationality": "Australian"},
    {"code": "SAI", "full_name": "Carlos Sainz",          "number": 55, "nationality": "Spanish"},
    {"code": "HAM", "full_name": "Lewis Hamilton",        "number": 44, "nationality": "British"},
    {"code": "RUS", "full_name": "George Russell",        "number": 63, "nationality": "British"},
    {"code": "ANT", "full_name": "Kimi Antonelli",        "number": 12, "nationality": "Italian"},
    {"code": "ALO", "full_name": "Fernando Alonso",       "number": 14, "nationality": "Spanish"},
    {"code": "STR", "full_name": "Lance Stroll",          "number": 18, "nationality": "Canadian"},
    {"code": "GAS", "full_name": "Pierre Gasly",          "number": 10, "nationality": "French"},
    {"code": "COL", "full_name": "Jack Doohan",           "number": 7,  "nationality": "Australian"},
    {"code": "ALB", "full_name": "Alexander Albon",       "number": 23, "nationality": "Thai"},
    {"code": "SAR", "full_name": "Logan Sargeant",        "number": 2,  "nationality": "American"},
    {"code": "HUL", "full_name": "Nico Hulkenberg",       "number": 27, "nationality": "German"},
    {"code": "OCO", "full_name": "Esteban Ocon",          "number": 31, "nationality": "French"},
    {"code": "MAG", "full_name": "Kevin Magnussen",       "number": 20, "nationality": "Danish"},
    {"code": "BEA", "full_name": "Oliver Bearman",        "number": 87, "nationality": "British"},
    {"code": "TSU", "full_name": "Yuki Tsunoda",          "number": 22, "nationality": "Japanese"},
    {"code": "LAW", "full_name": "Liam Lawson",           "number": 30, "nationality": "New Zealander"},
    {"code": "HAD", "full_name": "Isack Hadjar",          "number": 6,  "nationality": "French"},
    {"code": "BOT", "full_name": "Valtteri Bottas",       "number": 77, "nationality": "Finnish"},
    {"code": "ZHO", "full_name": "Guanyu Zhou",           "number": 24, "nationality": "Chinese"},
    # Historical
    {"code": "PER", "full_name": "Sergio Perez",          "number": 11, "nationality": "Mexican"},
    {"code": "RIC", "full_name": "Daniel Ricciardo",      "number": 3,  "nationality": "Australian"},
    {"code": "VET", "full_name": "Sebastian Vettel",      "number": 5,  "nationality": "German"},
    {"code": "RAI", "full_name": "Kimi Raikkonen",        "number": 7,  "nationality": "Finnish"},
    {"code": "GRO", "full_name": "Romain Grosjean",       "number": 8,  "nationality": "French"},
    {"code": "KVY", "full_name": "Daniil Kvyat",          "number": 26, "nationality": "Russian"},
    {"code": "GIO", "full_name": "Antonio Giovinazzi",    "number": 99, "nationality": "Italian"},
    {"code": "MSC", "full_name": "Mick Schumacher",       "number": 47, "nationality": "German"},
    {"code": "MAZ", "full_name": "Nikita Mazepin",        "number": 9,  "nationality": "Russian"},
    {"code": "FIT", "full_name": "Pietro Fittipaldi",     "number": 51, "nationality": "Brazilian"},
    {"code": "DEV", "full_name": "Nyck de Vries",         "number": 21, "nationality": "Dutch"},
]


# ---------------------------------------------------------------------------
# Build lookup indices
# ---------------------------------------------------------------------------

def _normalize(s: str) -> str:
    """Lowercase, strip accents, remove non-alphanumeric."""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _load_cache() -> list[DriverRecord]:
    if DRIVERS_CACHE.exists():
        return json.loads(DRIVERS_CACHE.read_text(encoding="utf-8"))
    return []


def _build_indices(records: list[DriverRecord]) -> dict:
    by_code:    dict[str, DriverRecord] = {}
    by_number:  dict[int, list[DriverRecord]] = {}
    by_surname: dict[str, list[DriverRecord]] = {}
    by_norm:    dict[str, DriverRecord] = {}

    for r in records:
        code = r.get("code", "").upper()
        if code:
            by_code[code] = r

        nums = set()
        if r.get("number") is not None:
            nums.add(int(r["number"]))
        for v in (r.get("numbers") or {}).values():
            if v is not None:
                nums.add(int(v))
        for num in nums:
            by_number.setdefault(num, []).append(r)

        parts = r.get("full_name", "").split()
        if parts:
            surname = _normalize(parts[-1])
            by_surname.setdefault(surname, []).append(r)

        full_norm = _normalize(r.get("full_name", ""))
        if full_norm:
            by_norm[full_norm] = r

    return {
        "by_code":    by_code,
        "by_number":  by_number,
        "by_surname": by_surname,
        "by_norm":    by_norm,
    }


_indices: dict | None = None


def _get_indices() -> dict:
    global _indices
    if _indices is None:
        cached = _load_cache()
        all_records = {r["code"]: r for r in KNOWN_DRIVERS}
        for r in cached:
            if r.get("code"):
                all_records[r["code"]] = r
        _indices = _build_indices(list(all_records.values()))
    return _indices


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class DriverResolver:
    """
    Resolve a raw name or car number to a canonical driver record.

    Usage:
        resolver = DriverResolver()
        rec = resolver.resolve_name("Hamilton")
        rec = resolver.resolve_number(44)
        rec = resolver.resolve_name("VER")
    """

    def __init__(self):
        self._idx = _get_indices()

    def resolve_name(self, raw: str, season: int | None = None) -> DriverRecord | None:
        """
        Resolve a driver name/code string to a canonical record.

        Tries: exact code → full name normalised → surname → partial match.
        """
        if not raw or not raw.strip():
            return None

        raw = raw.strip()
        idx = self._idx

        # 1. Exact 3-letter code: VER, HAM
        upper = raw.upper()
        if len(upper) == 3 and upper in idx["by_code"]:
            return idx["by_code"][upper]

        # 2. Normalised full name: "Lewis Hamilton" → "lewishamilton"
        norm = _normalize(raw)
        if norm in idx["by_norm"]:
            return idx["by_norm"][norm]

        # 3. Surname only: "Hamilton"
        surname = _normalize(raw.split()[-1])
        candidates = idx["by_surname"].get(surname, [])
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1 and season:
            for c in candidates:
                if season in c.get("seasons", []):
                    return c
            return candidates[0]

        # 4. Partial: "M. Verstappen" → surname "verstappen"
        parts = raw.split()
        if len(parts) >= 2:
            last = _normalize(parts[-1])
            candidates = idx["by_surname"].get(last, [])
            if candidates:
                return candidates[0]

        log.debug("DriverResolver: no match for %r", raw)
        return None

    def resolve_number(self, number: int, season: int | None = None) -> DriverRecord | None:
        """Resolve a car number to a driver. Uses season to disambiguate."""
        # Champion's car #1: per-season holder is curated (the upstream
        # API only exposes current numbers)
        if season and int(number) == 1 and season in CHAMPION_NUMBER_BY_SEASON:
            champ = self._idx["by_code"].get(CHAMPION_NUMBER_BY_SEASON[season])
            if champ:
                return champ
        candidates = self._idx["by_number"].get(int(number), [])
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        if season:
            # Exact per-season number match beats everything
            for c in candidates:
                if (c.get("numbers") or {}).get(str(season)) == int(number):
                    return c
            for c in candidates:
                if season in c.get("seasons", []):
                    return c
        # No season given: prefer the current holder of the number
        for c in candidates:
            if c.get("number") == int(number):
                return c
        return candidates[0]

    def resolve(self, name: str | None = None, number: int | None = None,
                season: int | None = None) -> DriverRecord | None:
        """Try name first, then number."""
        if name:
            r = self.resolve_name(name, season)
            if r:
                return r
        if number is not None:
            return self.resolve_number(number, season)
        return None
