"""Tests for packages.pipeline.linkers.race_control_linker.

The linker used to anchor on the decision's publication time with a 30-minute
window, which is paperwork time rather than incident time, and matched a driver
by looking for the code anywhere in the message. These fix the rules it uses
now: the cars the message names, the turn it names, and the time the decision
says the incident happened.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from packages.pipeline.linkers.race_control_linker import (
    WINDOW_AFTER_AGREED_S,
    WINDOW_AFTER_S,
    WINDOW_BEFORE_S,
    cars_named,
    message_matches_incident,
    offence_named,
    turn_named,
)

INCIDENT_AT = datetime(2024, 5, 26, 14, 30, 0, tzinfo=UTC)


_SAME_MOMENT = object()


def _match(message, *, at=_SAME_MOMENT, driver_number=None, cars=frozenset({44}),
           incident_time=INCIDENT_AT, corner=None, category=None):
    return message_matches_incident(
        message       = message,
        message_date  = incident_time if at is _SAME_MOMENT else at,
        driver_number = driver_number,
        car_numbers   = set(cars),
        incident_time = incident_time,
        corner        = corner,
        infraction_category = category,
    )


# ---------------------------------------------------------------------------
# cars_named
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("message,expected", [
    ("CAR 44 (HAM) TIME DELETED", {44}),
    ("TURN 17 INCIDENT INVOLVING CARS 44 (HAM) AND 55 (SAI) NOTED", {44, 55}),
    ("CAR NO.16 (LEC) UNDER INVESTIGATION", {16}),
    ("CAR NO. 1 (VER) NOTED", {1}),
    ("WAVED BLUE FLAG FOR CAR 2 (SAR)", {2}),
    ("TRACK CLEAR", set()),
    ("DRS ENABLED", set()),
])
def test_cars_named(message, expected):
    assert cars_named(message) == expected


def test_the_driver_number_column_counts_as_a_named_car():
    # OpenF1 sometimes states the car in the field rather than in the prose.
    assert cars_named("INCIDENT NOTED", driver_number=63) == {63}


def test_a_lap_time_is_not_a_car_number():
    # "CAR 11 (PER) TIME 1:23.092 DELETED" — 1, 23 and 92 are not cars.
    assert cars_named("CAR 11 (PER) TIME 1:23.092 DELETED - TRACK LIMITS") == {11}


# ---------------------------------------------------------------------------
# turn_named
# ---------------------------------------------------------------------------

def test_turn_named():
    assert turn_named("TURN 17 INCIDENT INVOLVING CARS 44 AND 55") == "17"
    assert turn_named("CAR 4 (NOR) NOTED - LEAVING THE TRACK") is None


# ---------------------------------------------------------------------------
# message_matches_incident — the car has to be one of the ruling's own
# ---------------------------------------------------------------------------

def test_a_message_about_another_car_does_not_belong_to_this_ruling():
    # The old rule linked any message inside a 30-minute window of the
    # decision's publication, so a blue flag for a different car attached
    # itself to whichever incident was published nearby.
    assert _match("WAVED BLUE FLAG FOR CAR 2 (SAR) TIMED AT 15:16:49") is False


def test_a_message_naming_the_ruling_s_car_belongs_to_it():
    assert _match("CAR 44 (HAM) NOTED - CROSSING THE TRACK") is True


def test_a_message_naming_two_cars_belongs_to_both_rulings():
    msg = "TURN 17 INCIDENT INVOLVING CARS 44 (HAM) AND 55 (SAI) NOTED"
    assert _match(msg, cars={44}) is True
    assert _match(msg, cars={55}) is True


def test_an_incident_with_no_car_numbers_matches_nothing():
    # Protests, promoter decisions and panel changes name no driver at all.
    assert _match("CAR 44 (HAM) NOTED", cars=set()) is False


# ---------------------------------------------------------------------------
# message_matches_incident — the window
# ---------------------------------------------------------------------------

def test_race_control_notes_the_incident_afterwards():
    later = INCIDENT_AT + timedelta(seconds=WINDOW_AFTER_S - 1)
    assert _match("CAR 44 (HAM) NOTED", at=later) is True


def test_a_message_a_whole_session_later_is_a_different_incident():
    later = INCIDENT_AT + timedelta(seconds=WINDOW_AFTER_S + 1)
    assert _match("CAR 44 (HAM) NOTED", at=later) is False


def test_the_window_is_asymmetric():
    # Race control does not report an incident before it happens; the small
    # negative tolerance only absorbs the minute the decision rounds to.
    before = INCIDENT_AT - timedelta(seconds=WINDOW_BEFORE_S + 1)
    assert _match("CAR 44 (HAM) NOTED", at=before) is False
    assert WINDOW_AFTER_S > WINDOW_BEFORE_S


def test_the_stewards_own_announcement_arrives_after_the_ordinary_window():
    # "WILL BE INVESTIGATED" and the penalty itself land well past the p90 of
    # the noting message. Naming the same offence is what identifies them.
    late = INCIDENT_AT + timedelta(seconds=WINDOW_AFTER_S + 300)
    assert _match(
        "FIA STEWARDS: INCIDENT INVOLVING CAR 44 (HAM) NOTED - YELLOW FLAG INFRINGEMENT",
        at=late, category="yellow_flag",
    ) is True


def test_the_longer_window_is_not_offered_without_offence_agreement():
    late = INCIDENT_AT + timedelta(seconds=WINDOW_AFTER_S + 300)
    # Same message, same lateness, but the ruling is for something else.
    assert _match(
        "FIA STEWARDS: INCIDENT INVOLVING CAR 44 (HAM) NOTED - YELLOW FLAG INFRINGEMENT",
        at=late, category="collision",
    ) is False
    # And a message that names no offence at all cannot reach that far either.
    assert _match("CAR 44 (HAM) NOTED", at=late, category="yellow_flag") is False


def test_even_the_longer_window_ends():
    too_late = INCIDENT_AT + timedelta(seconds=WINDOW_AFTER_AGREED_S + 1)
    assert _match(
        "FIA STEWARDS: INCIDENT INVOLVING CAR 44 (HAM) NOTED - YELLOW FLAG INFRINGEMENT",
        at=too_late, category="yellow_flag",
    ) is False


# ---------------------------------------------------------------------------
# message_matches_incident — the turn
# ---------------------------------------------------------------------------

def test_a_different_turn_is_a_different_incident():
    # Verbatim: a driver with two decisions in one session, minutes apart.
    assert _match(
        "TURN 5 INCIDENT INVOLVING CARS 30 (LAW) AND 11 (PER) NOTED",
        cars={11}, corner="4",
    ) is False


def test_the_same_turn_confirms_it():
    assert _match(
        "TURN 4 INCIDENT INVOLVING CARS 18 (STR) AND 11 (PER) NOTED",
        cars={11}, corner="4",
    ) is True


def test_a_message_with_no_turn_is_not_rejected_by_one():
    assert _match("CAR 11 (PER) UNDER INVESTIGATION", cars={11}, corner="4") is True


def test_a_ruling_with_no_stated_corner_does_not_filter_on_one():
    assert _match(
        "TURN 5 INCIDENT INVOLVING CARS 30 (LAW) AND 11 (PER) NOTED",
        cars={11}, corner=None,
    ) is True


# ---------------------------------------------------------------------------
# offence_named
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("message,expected", [
    ("CAR 44 (HAM) TIME 1:10.981 DELETED - TRACK LIMITS AT TURN 10", "track_limits"),
    ("CAR 81 (PIA) LAP DELETED - DOUBLE YELLOW AT TURN 1", "yellow_flag"),
    ("TURN 1 INCIDENT INVOLVING CARS 4 AND 1 NOTED - CAUSING A COLLISION", "collision"),
    ("CAR 27 (HUL) NOTED - VIRTUAL SAFETY CAR INFRINGEMENT", "vsc"),
    ("CAR 27 (HUL) NOTED - SAFETY CAR INFRINGEMENT", "safety_car"),
    ("FIA STEWARDS: 5 SECOND TIME PENALTY FOR CAR 44 (HAM)", None),
    ("WAVED BLUE FLAG FOR CAR 2 (SAR)", None),
])
def test_offence_named(message, expected):
    assert offence_named(message) == expected


def test_virtual_safety_car_is_not_read_as_safety_car():
    # "SAFETY CAR INFRINGEMENT" is a substring of the virtual one, so reading
    # the phrases in the wrong order sorted every VSC ruling into safety_car.
    assert offence_named("CAR 27 (HUL) NOTED - VIRTUAL SAFETY CAR INFRINGEMENT") == "vsc"


# ---------------------------------------------------------------------------
# message_matches_incident — a deleted lap time records one offence
# ---------------------------------------------------------------------------

def test_a_deleted_lap_time_does_not_belong_to_a_collision_ruling():
    # Verbatim, inside the window of a collision decision against the same car.
    assert _match(
        "CAR 20 (MAG) TIME 1:39.463 DELETED - TRACK LIMITS AT TURN 4 LAP 10",
        cars={20}, category="collision",
    ) is False


def test_a_deleted_lap_time_belongs_to_the_track_limits_ruling():
    assert _match(
        "CAR 20 (MAG) TIME 1:39.463 DELETED - TRACK LIMITS AT TURN 4 LAP 10",
        cars={20}, category="track_limits",
    ) is True


def test_a_deletion_for_a_yellow_flag_belongs_to_the_yellow_flag_ruling():
    # Deleted-lap-time documents cover both reasons; the message says which.
    assert _match("CAR 44 (HAM) LAP DELETED - DOUBLE YELLOW AT TURN 2",
                  category="yellow_flag") is True
    assert _match("CAR 44 (HAM) LAP DELETED - DOUBLE YELLOW AT TURN 2",
                  category="track_limits") is False


def test_a_deletion_is_not_filtered_against_a_ruling_race_control_cannot_name():
    # Parc fermé, 107%, technical — race control never prints these, so there
    # is nothing for the message to agree with.
    assert _match("CAR 44 (HAM) LAP DELETED - TRACK LIMITS AT TURN 2",
                  category="parc_ferme") is True


# ---------------------------------------------------------------------------
# message_matches_incident — no stated incident time
# ---------------------------------------------------------------------------

def test_without_a_stated_time_only_investigation_wording_counts():
    assert _match("CAR 44 (HAM) UNDER INVESTIGATION",
                  at=INCIDENT_AT, incident_time=None) is True
    assert _match("WAVED BLUE FLAG FOR CAR 44 (HAM)",
                  at=INCIDENT_AT, incident_time=None) is False


def test_without_a_stated_time_the_offence_has_to_agree():
    # "Doc 108 - Infringement - Race Deleted Lap Times" names eighteen drivers
    # and no time. On wording alone it collected every message any of them
    # appeared in — and missed the deletions that are the actual record.
    untimed = {"at": INCIDENT_AT, "incident_time": None, "category": "track_limits"}
    assert _match("CAR 44 (HAM) NOTED - STARTING PROCEDURE INFRINGEMENT", **untimed) is False
    assert _match("FIA STEWARDS: 5 SECOND TIME PENALTY FOR CAR 44 (HAM)", **untimed) is False
    assert _match("CAR 44 (HAM) TIME 1:10.981 DELETED - TRACK LIMITS AT TURN 10",
                  **untimed) is True


def test_without_a_stated_time_an_unspoken_category_falls_back_to_wording():
    # The SC2-SC1 maximum time decisions have a category race control never
    # prints; holding them to an offence would link them to nothing at all.
    assert _match("CAR 44 (HAM) UNDER INVESTIGATION", at=INCIDENT_AT,
                  incident_time=None, category="safety_car_line_time") is True


def test_a_message_with_no_date_cannot_be_placed_against_a_timed_incident():
    assert _match("CAR 44 (HAM) NOTED", at=None, incident_time=INCIDENT_AT) is False


# ---------------------------------------------------------------------------
# fetch_and_store_rc_messages — the dedup key
# ---------------------------------------------------------------------------

class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDB:
    """Just enough of an AsyncSession to exercise the dedup branch."""

    def __init__(self, stored):
        self.stored = stored
        self.added = []

    async def execute(self, _stmt):
        return _FakeResult(self.stored)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass


class _Row:
    def __init__(self, date, message):
        self.date = date
        self.message = message


def test_a_message_already_stored_is_not_inserted_again():
    # The dedup key was built from str(row.date) on one side and OpenF1's raw
    # string on the other — "2024-05-26 14:30:00+00:00" against
    # "2024-05-26T14:30:00+00:00". It never matched, so every re-run of the
    # backfill inserted the whole session again: 12,437 duplicate rows.
    from packages.pipeline.linkers.race_control_linker import RaceControlLinker

    linker = RaceControlLinker.__new__(RaceControlLinker)
    linker._client = type(
        "C", (), {"race_control": staticmethod(lambda session_key: [
            {"date": "2024-05-26T14:30:00+00:00", "message": "CAR 44 (HAM) NOTED"},
            {"date": "2024-05-26T14:31:00+00:00", "message": "CAR 55 (SAI) NOTED"},
        ])},
    )()

    db = _FakeDB([_Row(INCIDENT_AT, "CAR 44 (HAM) NOTED")])
    assert asyncio.run(linker.fetch_and_store_rc_messages(9158, db)) == 1
    assert [rc.message for rc in db.added] == ["CAR 55 (SAI) NOTED"]


def test_one_response_carrying_the_same_message_twice_inserts_it_once():
    from packages.pipeline.linkers.race_control_linker import RaceControlLinker

    linker = RaceControlLinker.__new__(RaceControlLinker)
    linker._client = type(
        "C", (), {"race_control": staticmethod(lambda session_key: [
            {"date": "2024-05-26T14:30:00+00:00", "message": "CAR 44 (HAM) NOTED"},
            {"date": "2024-05-26T14:30:00+00:00", "message": "CAR 44 (HAM) NOTED"},
        ])},
    )()

    db = _FakeDB([])
    assert asyncio.run(linker.fetch_and_store_rc_messages(9158, db)) == 1
