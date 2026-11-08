import random
import uuid
from datetime import UTC, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from riso.shared import FixedClock, UuidV7Generator, new_id, uuid7_time

T0 = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


def generator(clock: FixedClock, seed: int = 0) -> UuidV7Generator:
    return UuidV7Generator(clock, random.Random(seed).getrandbits)


def test_ids_are_uuidv7_with_the_rfc_variant():
    value = uuid.UUID(new_id())
    assert value.version == 7
    assert value.variant == uuid.RFC_4122


def test_ids_made_in_one_millisecond_are_unique_and_in_order():
    ids = generator(FixedClock(T0))
    made = [ids.new() for _ in range(5000)]
    assert len(set(made)) == len(made)
    assert made == sorted(made)


def test_ids_sort_by_creation_time_across_milliseconds():
    clock = FixedClock(T0)
    ids = generator(clock)
    made = []
    for _ in range(200):
        made.append(ids.new())
        clock.advance(timedelta(microseconds=700))
    assert made == sorted(made)


def test_ids_stay_in_order_when_the_clock_steps_back():
    clock = FixedClock(T0)
    ids = generator(clock)
    first = ids.new()
    clock.advance(timedelta(seconds=-5))
    assert ids.new() > first


def test_an_exhausted_counter_borrows_the_next_millisecond():
    # randbits always returning its maximum starts every counter at 2047, so it runs out
    # after 2048 IDs in one millisecond.
    ids = UuidV7Generator(FixedClock(T0), lambda bits: (1 << bits) - 1)
    made = [ids.new() for _ in range(3000)]
    assert made == sorted(made)
    assert len(set(made)) == 3000
    assert uuid7_time(made[0]) == T0
    assert uuid7_time(made[-1]) == T0 + timedelta(milliseconds=1)


@given(st.datetimes(min_value=datetime(1990, 1, 1), max_value=datetime(2200, 1, 1)))
def test_the_creation_time_can_be_read_back_to_the_millisecond(at):
    at = at.replace(tzinfo=UTC)
    made = generator(FixedClock(at)).new()
    assert uuid7_time(made) == at.replace(microsecond=at.microsecond // 1000 * 1000)
