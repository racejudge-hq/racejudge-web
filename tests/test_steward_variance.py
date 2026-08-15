"""Tests for the penalty-severity ladder behind /v1/incidents/variance.

mean_severity is the only number in the variance endpoints that claims to
compare *how harshly* panels rule, so a code that falls off the ladder is
worse than useless: it reads as leniency the panel never showed.
"""

from __future__ import annotations

import pytest

from apps.api.routers.stewards import (
    PENALTY_ORDER,
    _entropy,
    _inconsistency_score,
    _mean_severity,
    _modal,
    _severity,
)


@pytest.mark.parametrize("code", ["WARN", "FINE", "SG", "PIT"])
def test_every_real_penalty_outranks_no_further_action(code: str) -> None:
    # These four were absent from the ladder and scored 0, identical to NFA.
    assert _severity(code) > _severity("NFA")


def test_the_ladder_runs_in_the_order_the_guidelines_set_out() -> None:
    rungs = ["NFA", "WARN", "REP", "FINE", "5s", "10s", "DT", "SG", "GRID", "DSQ"]
    scores = [_severity(c) for c in rungs]
    assert scores == sorted(scores)
    assert len(set(scores)) == len(scores)


def test_longer_time_penalties_score_higher() -> None:
    assert _severity("5s") < _severity("10s") < _severity("20s")


def test_no_time_penalty_outranks_a_drive_through() -> None:
    # A 30s penalty is still a time penalty; the guidelines place the whole
    # family below a drive-through.
    assert _severity("30s") < _severity("DT")


def test_a_pit_lane_start_ranks_with_a_grid_drop() -> None:
    assert _severity("PIT") == _severity("GRID")


def test_an_unknown_code_scores_zero_rather_than_raising() -> None:
    assert _severity("WHAT") == 0.0
    assert _severity("") == 0.0


def test_severity_never_exceeds_disqualification() -> None:
    assert all(v <= PENALTY_ORDER["DSQ"] for v in PENALTY_ORDER.values())


def test_mean_severity_separates_a_lenient_panel_from_a_harsh_one() -> None:
    lenient = {"NFA": 8, "WARN": 2}
    harsh   = {"DSQ": 5, "GRID": 5}
    assert _mean_severity(lenient) < _mean_severity(harsh)


def test_mean_severity_of_nothing_is_zero() -> None:
    assert _mean_severity({}) == 0.0


def test_a_panel_that_always_rules_the_same_way_is_perfectly_consistent() -> None:
    assert _entropy({"NFA": 40}) == 0.0
    assert _inconsistency_score({"NFA": 40}) == 0.0


def test_an_even_split_is_maximally_inconsistent() -> None:
    assert _inconsistency_score({"NFA": 10, "DSQ": 10}) == 1.0


def test_modal_penalty_of_nothing_defaults_to_no_further_action() -> None:
    assert _modal({}) == "NFA"
