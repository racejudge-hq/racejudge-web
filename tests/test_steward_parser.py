"""
Tests for the steward signature-block parser.

The word layouts below are the real ones: x/top coordinates taken from FIA
decision PDFs in the corpus. The left column starts at x0=46 and the right at
x0=300, a gap far wider than any within-name spacing.
"""

from __future__ import annotations

import pytest

from packages.pipeline.parsers.steward_parser import (
    DRIVER_STEWARDS,
    StewardPanel,
    _looks_like_name,
    parse_panel_from_words,
)


def _row(top: float, *cells: tuple[float, str]) -> list[dict]:
    """Lay out one printed line: each cell is (x0, text), words 6pt apart."""
    words = []
    for x0, text in cells:
        x = x0
        for token in text.split():
            width = 7.5 * len(token)
            words.append({"text": token, "x0": x, "x1": x + width, "top": top})
            x += width + 6.0
    return words


def _page(*rows: list[dict]) -> list[dict]:
    return [w for row in rows for w in row]


# 2024 Chinese GP, Doc 68 — the ordinary four-name panel.
FOUR_NAME = _page(
    _row(521.9, (118.6, "Competitors are reminded that they have the right to appeal")),
    _row(546.9, (118.6, "Chapter 4 of the FIA Judicial and Disciplinary Rules.")),
    _row(672.5, (46.0, "Nish Shetty"), (300.3, "Loïc Bacquelaine")),
    _row(703.0, (46.0, "Vitantonio Liuzzi"), (300.3, "Zheng Honghai")),
    _row(733.6, (46.0, "The Stewards")),
)

# 2026 Japanese GP, Doc 23 — five stewards, the grid runs 3 + 2.
FIVE_NAME = _page(
    _row(609.5, (118.6, "on the relevant regulations, guidelines and evidence presented.")),
    _row(672.5, (46.0, "Nish Shetty"), (300.3, "Dennis Dean")),
    _row(703.0, (46.0, "Loic Bacquelaine"), (300.3, "Emanuele Pirro")),
    _row(733.6, (46.0, "Eric Cowcill")),
    _row(764.0, (46.0, "The Stewards")),
)

# A PU-elements tally sheet: signed by one delegate, no panel at all.
DELEGATE_ONLY = _page(
    _row(600.0, (46.0, "Jo Bauer")),
    _row(630.0, (46.0, "The FIA Formula One Technical Delegate")),
)


def test_four_name_panel_reads_column_major() -> None:
    panel = parse_panel_from_words(FOUR_NAME)
    assert panel == StewardPanel(
        chair="Nish Shetty",
        members=("Nish Shetty", "Vitantonio Liuzzi", "Loïc Bacquelaine", "Zheng Honghai"),
        driver_steward="Vitantonio Liuzzi",
    )


def test_the_chair_is_the_top_of_the_left_column() -> None:
    # Not simply the first name in reading order: reading order would give
    # "Nish Shetty Loïc Bacquelaine" as one line and lose the structure.
    assert parse_panel_from_words(FOUR_NAME).chair == "Nish Shetty"


def test_five_name_panel_keeps_the_left_column_first() -> None:
    panel = parse_panel_from_words(FIVE_NAME)
    assert panel.chair == "Nish Shetty"
    assert panel.members == (
        "Nish Shetty", "Loic Bacquelaine", "Eric Cowcill", "Dennis Dean", "Emanuele Pirro",
    )
    # The driver steward is last here, not second — found by name, not position.
    assert panel.driver_steward == "Emanuele Pirro"


def test_a_delegate_signoff_is_not_a_panel() -> None:
    assert parse_panel_from_words(DELEGATE_ONLY) is None


def test_appeal_boilerplate_never_leaks_into_the_panel() -> None:
    panel = parse_panel_from_words(FOUR_NAME)
    assert all("Chapter" not in n and "Competitors" not in n for n in panel.members)
    assert len(panel.members) == 4


def test_a_page_without_a_signoff_yields_nothing() -> None:
    body = _page(_row(100.0, (118.6, "The Stewards have considered the matter.")))
    assert parse_panel_from_words(body) is None


def test_signature_block_may_sit_at_the_top_of_a_page() -> None:
    # A decision that runs onto a second page signs at the top of it. Nothing
    # in the parser may assume the block is near the foot of the page.
    top_of_page = _page(
        _row(51.4, (118.6, "Decisions of the Stewards are taken independently of the FIA.")),
        _row(131.0, (46.0, "Nish Shetty"), (300.3, "Loïc Bacquelaine")),
        _row(161.5, (46.0, "Vitantonio Liuzzi"), (300.3, "Zheng Honghai")),
        _row(192.1, (46.0, "The Stewards")),
    )
    assert parse_panel_from_words(top_of_page).chair == "Nish Shetty"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Nish Shetty", True),
        ("Loïc Bacquelaine", True),
        ("Mazen Al Hilli", True),
        ("Alfonso Oros Trigueros", True),
        ("Bauer", False),                       # a single token is not a full name
        ("The Stewards", False),                # sign-off, not a person
        ("FIA Formula One Technical Delegate", False),
        ("Chapter 4 of the", False),            # boilerplate with a digit
        ("Article 15", False),
    ],
)
def test_looks_like_name(text: str, expected: bool) -> None:
    assert _looks_like_name(text) is expected


def test_driver_stewards_are_disjoint_from_the_chairs() -> None:
    # The five chairs observed across the corpus are FIA stewards, never the
    # driver member. If one ever appeared in both roles the panel read is wrong.
    chairs = {"Garry Connelly", "Nish Shetty", "Gerd Ennser", "Felix Holter", "Tim Mayer"}
    assert chairs.isdisjoint(DRIVER_STEWARDS)


def test_a_misread_grid_with_a_repeated_name_is_rejected() -> None:
    duplicated = _page(
        _row(672.5, (46.0, "Nish Shetty"), (300.3, "Nish Shetty")),
        _row(703.0, (46.0, "Derek Warwick"), (300.3, "Zheng Honghai")),
        _row(733.6, (46.0, "The Stewards")),
    )
    assert parse_panel_from_words(duplicated) is None
