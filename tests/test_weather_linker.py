"""Tests for packages.pipeline.linkers.weather_linker.

`weather_context` states what the conditions were at a moment. Every test here
defends the same rule: if the moment is not known, or the nearest reading is
too far from it to describe it, the answer is None rather than a number.
"""

from datetime import UTC, datetime, timedelta

import pytest

from packages.pipeline.linkers.weather_linker import (
    MAX_WEATHER_GAP_S,
    WeatherLinker,
)

AT = datetime(2024, 5, 26, 14, 30, tzinfo=UTC)


def linker_with(rows: list[dict]) -> WeatherLinker:
    """A linker holding fixed readings, with no OpenF1 client behind it.

    __init__ constructs a network client; this bypasses it so the tests
    exercise the selection rule and nothing else.
    """
    obj = object.__new__(WeatherLinker)
    obj._client = None
    obj._cache = {9158: rows}
    return obj


def reading(at: datetime, **over) -> dict:
    row = {
        "date": at.isoformat(),
        "air_temperature": 28.5,
        "track_temperature": 41.0,
        "humidity": 58.0,
        "rainfall": 0,
        "wind_speed": 1.4,
        "wind_direction": 210,
        "pressure": 1014.3,
    }
    row.update(over)
    return row


def test_an_incident_with_no_time_has_no_weather():
    # The 11 rows scripts/clear_unanchored_weather.py removed were all of this
    # shape: real-looking weather on an incident nothing can place in time.
    assert linker_with([reading(AT)]).get_weather_at_incident(9158, None) is None


def test_a_reading_beyond_the_gap_ceiling_is_not_this_incident_s_weather():
    far = AT + timedelta(seconds=MAX_WEATHER_GAP_S + 1)
    assert linker_with([reading(far)]).get_weather_at_incident(9158, AT) is None


def test_the_nearest_reading_wins():
    rows = [
        reading(AT - timedelta(seconds=300), air_temperature=20.0),
        reading(AT + timedelta(seconds=30), air_temperature=29.0),
        reading(AT + timedelta(seconds=240), air_temperature=25.0),
    ]
    got = linker_with(rows).get_weather_at_incident(9158, AT)
    assert got["air_temp"] == 29.0
    assert got["timestamp_delta_s"] == 30.0


def test_the_distance_to_the_reading_is_reported_with_it():
    # A consumer cannot judge the value without knowing how far off it was.
    got = linker_with([reading(AT + timedelta(seconds=95))]).get_weather_at_incident(9158, AT)
    assert got["timestamp_delta_s"] == 95.0


def test_rainfall_is_a_bool_whatever_openf1_sends():
    got = linker_with([reading(AT, rainfall=1)]).get_weather_at_incident(9158, AT)
    assert got["rainfall"] is True
    got = linker_with([reading(AT, rainfall=0)]).get_weather_at_incident(9158, AT)
    assert got["rainfall"] is False


def test_a_session_with_no_readings_has_no_weather():
    assert linker_with([]).get_weather_at_incident(9158, AT) is None


def test_an_unparseable_timestamp_is_skipped_not_fatal():
    rows = [reading(AT, date="not a date"), reading(AT + timedelta(seconds=10))]
    got = linker_with(rows).get_weather_at_incident(9158, AT)
    assert got["timestamp_delta_s"] == 10.0


@pytest.mark.parametrize("stamp", [
    "2024-05-26T14:30:00+00:00",
    "2024-05-26T14:30:00Z",
    "2024-05-26T14:30:00.500Z",
])
def test_openf1_timestamp_spellings_all_parse(stamp):
    # strptime did not handle the offset or the fractional seconds; both forms
    # appear in the feed, and a row that fails to parse is a row silently lost.
    got = linker_with([reading(AT, date=stamp)]).get_weather_at_incident(9158, AT)
    assert got is not None
    assert got["timestamp_delta_s"] < 1.0


def test_a_naive_timestamp_is_read_as_utc():
    # Without a tzinfo the subtraction raises, and the row is dropped by the
    # except -- so a whole session of naive stamps would report no weather.
    got = linker_with([reading(AT, date="2024-05-26T14:30:00")]).get_weather_at_incident(9158, AT)
    assert got is not None
    assert got["timestamp_delta_s"] == 0.0
