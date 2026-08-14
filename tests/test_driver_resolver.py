"""Tests for driver_resolver.py"""

import pytest

from packages.pipeline.resolvers.driver_resolver import DriverResolver


@pytest.fixture
def r():
    return DriverResolver()


def test_resolve_code_exact(r):
    rec = r.resolve_name("VER")
    assert rec is not None
    assert rec["code"] == "VER"
    assert "Verstappen" in rec["full_name"]


def test_resolve_code_lowercase(r):
    # "ham".upper() == "HAM" which is in the index — should resolve
    rec = r.resolve_name("ham")
    assert rec is not None
    assert rec["code"] == "HAM"


def test_resolve_full_name(r):
    rec = r.resolve_name("Max Verstappen")
    assert rec is not None
    assert rec["code"] == "VER"


def test_resolve_surname_only(r):
    rec = r.resolve_name("Hamilton")
    assert rec is not None
    assert rec["code"] == "HAM"


def test_resolve_surname_verstappen(r):
    rec = r.resolve_name("Verstappen")
    assert rec is not None
    assert rec["code"] == "VER"


def test_resolve_partial_name(r):
    rec = r.resolve_name("L. Norris")
    assert rec is not None
    assert rec["code"] == "NOR"


def test_resolve_number(r):
    rec = r.resolve_number(44)
    assert rec is not None
    assert rec["code"] == "HAM"


def test_resolve_number_verstappen(r):
    # Car #1 changes hands with the championship — pin the season so the
    # test stays valid as new rosters are fetched into data/reference.
    rec = r.resolve_number(1, season=2024)
    assert rec is not None
    assert rec["code"] == "VER"


def test_resolve_number_one_2026_champion(r):
    rec = r.resolve_number(1, season=2026)
    assert rec is not None
    assert rec["code"] == "NOR"


# Every pairing below is stated verbatim in a stored decision ("Driver 33 -
# Max Verstappen"), so these guard the per-season history against a reseed
# reintroducing the upstream permanent-number-for-every-season bug.
@pytest.mark.parametrize("number,season,code", [
    # Verstappen: 33 before the title, 1 while champion, 3 from 2026
    (33, 2019, "VER"), (33, 2020, "VER"), (33, 2021, "VER"),
    (1, 2022, "VER"), (1, 2025, "VER"), (3, 2026, "VER"),
    # Norris: 4 until he takes #1 in 2026
    (4, 2019, "NOR"), (4, 2024, "NOR"), (4, 2025, "NOR"), (1, 2026, "NOR"),
    # #3 is Ricciardo's for as long as he races — it must not fall to Verstappen
    (3, 2019, "RIC"), (3, 2022, "RIC"), (3, 2024, "RIC"),
    # Reserve and stand-in numbers
    (40, 2023, "LAW"), (37, 2024, "HAD"), (36, 2025, "LIN"),
    (38, 2024, "BEA"), (50, 2024, "BEA"), (97, 2024, "SHW"),
    # Unchanged numbers stay unchanged
    (44, 2021, "HAM"), (16, 2024, "LEC"), (81, 2025, "PIA"),
])
def test_resolve_number_per_season_history(r, number, season, code):
    rec = r.resolve_number(number, season=season)
    assert rec is not None, f"car {number} in {season} resolved to nobody"
    assert rec["code"] == code


def test_colapinto_and_doohan_are_distinct_fallback_records(r):
    # The built-in fallback list once paired code "COL" with Jack Doohan's
    # name, which the cached roster happened to mask.
    from packages.pipeline.resolvers.driver_resolver import KNOWN_DRIVERS
    by_code = {d["code"]: d for d in KNOWN_DRIVERS}
    assert "Colapinto" in by_code["COL"]["full_name"]
    assert "Doohan" in by_code["DOO"]["full_name"]


def test_resolve_unknown_name(r):
    rec = r.resolve_name("NotADriver")
    assert rec is None


def test_resolve_unknown_number(r):
    rec = r.resolve_number(99)
    # Raikkonen wore 7; Giovinazzi wore 99 — may or may not resolve
    # Just check no crash
    assert rec is None or isinstance(rec, dict)


def test_resolve_combined_name_and_number(r):
    rec = r.resolve(name="Hamilton", number=44)
    assert rec is not None
    assert rec["code"] == "HAM"


def test_resolve_name_takes_priority(r):
    # name=VER but number=44 (Hamilton) — name should win
    rec = r.resolve(name="VER", number=44)
    assert rec["code"] == "VER"


def test_resolve_empty_string(r):
    assert r.resolve_name("") is None


def test_resolve_none(r):
    assert r.resolve() is None
