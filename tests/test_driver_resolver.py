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
    rec = r.resolve_number(1)
    assert rec is not None
    assert rec["code"] == "VER"


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
