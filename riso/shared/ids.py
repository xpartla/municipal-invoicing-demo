"""Aggregate IDs: UUIDv7 strings (RFC 9562), which sort by creation time.

Python 3.12 has no `uuid.uuid7`, so the generator is written here. It follows RFC 9562
method 1: the 48-bit Unix time in milliseconds, then a 12-bit counter in `rand_a` that
keeps IDs made in the same millisecond in order, then 62 random bits. The domain never
makes IDs itself; it receives them from an `IdGenerator`.
"""

import secrets
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from riso.shared.clock import Clock, SystemClock

_COUNTER_MAX = 0xFFF


class IdGenerator(Protocol):
    def new(self) -> str:
        """A new, unique ID."""
        ...


class UuidV7Generator:
    """UUIDv7 IDs, strictly increasing for one generator even when the clock stands still
    or steps back. Thread-safe."""

    def __init__(
        self,
        clock: Clock | None = None,
        randbits: Callable[[int], int] = secrets.randbits,
    ) -> None:
        self._clock = clock or SystemClock()
        self._randbits = randbits
        self._lock = threading.Lock()
        self._last_ms = -1
        self._counter = 0

    def new(self) -> str:
        with self._lock:
            ms = int(self._clock.now().timestamp() * 1000)
            if ms > self._last_ms:
                self._last_ms = ms
                # Start the counter in its lower half, so it has room to grow (RFC 9562 6.2).
                self._counter = self._randbits(11)
            else:
                self._counter += 1
                if self._counter > _COUNTER_MAX:
                    # The counter is exhausted within this millisecond: borrow the next one.
                    self._last_ms += 1
                    self._counter = self._randbits(11)
            return str(_uuid7(self._last_ms, self._counter, self._randbits(62)))


def _uuid7(unix_ms: int, counter: int, rand_b: int) -> uuid.UUID:
    value = (unix_ms & 0xFFFF_FFFF_FFFF) << 80
    value |= 0x7 << 76  # version
    value |= (counter & _COUNTER_MAX) << 64
    value |= 0b10 << 62  # variant
    value |= rand_b & ((1 << 62) - 1)
    return uuid.UUID(int=value)


def uuid7_time(value: str) -> datetime:
    """When a UUIDv7 was made, to the millisecond."""
    parsed = uuid.UUID(value)
    if parsed.version != 7:
        raise ValueError("not a UUIDv7")
    return datetime.fromtimestamp((parsed.int >> 80) / 1000, tz=UTC)


_default = UuidV7Generator()


def new_id() -> str:
    """A UUIDv7 from the process-wide generator, for the edges (CLI, seeding). Use cases get
    their IDs from the unit of work's generator instead."""
    return _default.new()
