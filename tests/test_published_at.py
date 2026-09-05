"""Tests for fia_scraper.parse_published_at.

The FIA listing page's date element is the only record of when a decision was
published, and it arrives as text in two shapes with a timezone label that is
wrong for half the year.
"""

from datetime import UTC, datetime

import pytest

from packages.pipeline.scrapers.fia_scraper import parse_published_at


def test_the_labelled_shape_parses():
    # 1,447 of 1,606 rows look like this, with no space after "on".
    got = parse_published_at("Published on08.10.23 20:58CET")
    assert got == datetime(2023, 10, 8, 18, 58, tzinfo=UTC)


def test_the_bare_shape_parses():
    # The other 159, from a <time> element rather than a date-classed one.
    assert parse_published_at("07.12.25 15:59") == datetime(2025, 12, 7, 14, 59, tzinfo=UTC)


def test_a_summer_document_is_read_as_paris_local_not_fixed_utc_plus_one():
    # The page says "CET" in July too. Read literally that is UTC+1 and every
    # summer document lands an hour late -- which is what inflated the measured
    # publication lag from 132 to 192 minutes. Paris is UTC+2 in July.
    assert parse_published_at("Published on07.07.24 16:30CET") == datetime(
        2024, 7, 7, 14, 30, tzinfo=UTC
    )


def test_a_winter_document_is_utc_plus_one():
    assert parse_published_at("Published on07.01.24 16:30CET") == datetime(
        2024, 1, 7, 15, 30, tzinfo=UTC
    )


def test_the_day_comes_before_the_month():
    # "08.10.23" is 8 October, not 10 August. Reading it the other way puts a
    # document in the wrong season for two thirds of the calendar.
    assert parse_published_at("Published on08.10.23 20:58CET").month == 10


def test_the_result_is_ordered_chronologically_unlike_the_raw_string():
    # The whole point of the column. As text, "Published on..." sorts after
    # "07.12.25", and within the prefixed rows the day sorts before the month.
    raw = ["Published on08.10.23 20:58CET", "07.12.25 15:59", "Published on09.02.24 10:00CET"]
    assert sorted(raw) != raw  # the text order is not the true order
    assert [p.year for p in sorted(parse_published_at(r) for r in raw)] == [2023, 2024, 2025]


@pytest.mark.parametrize("raw", [
    None,
    "",
    "Published on",
    "no date here",
    "2023",           # a year alone does not place a document in time
    "08.10.23",       # a date with no time
])
def test_text_carrying_no_full_date_yields_none(raw):
    # NULL is the honest answer. A plausible-looking wrong instant is worse
    # than an absent one, because nothing downstream can tell it was guessed.
    assert parse_published_at(raw) is None


@pytest.mark.parametrize("raw", [
    "Published on31.02.23 10:00CET",   # no such day
    "Published on08.13.23 10:00CET",   # no such month
    "Published on08.10.23 25:00CET",   # no such hour
])
def test_an_impossible_date_yields_none_rather_than_raising(raw):
    assert parse_published_at(raw) is None


def test_the_returned_datetime_is_aware():
    # A naive datetime compared against an aware one raises, and this column is
    # compared against incident_time and session windows.
    assert parse_published_at("07.12.25 15:59").tzinfo is not None
