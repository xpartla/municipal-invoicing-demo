"""Time. Instants are timezone-aware UTC; days are counted in Europe/Bratislava.

The domain never calls `datetime.now()`: it receives the time from a `Clock`.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

BRATISLAVA = ZoneInfo("Europe/Bratislava")


class Clock(Protocol):
    def now(self) -> datetime:
        """The current instant, timezone-aware in UTC."""
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    """A clock that moves only when told to, for tests."""

    def __init__(self, at: datetime) -> None:
        self._at = _utc(at)

    def now(self) -> datetime:
        return self._at

    def set(self, at: datetime) -> None:
        self._at = _utc(at)

    def advance(self, delta: timedelta) -> None:
        self._at += delta


def local_date(instant: datetime) -> date:
    """The calendar day of an instant in Bratislava, which is the day the statistics and the
    booking date defaults use."""
    return _utc(instant).astimezone(BRATISLAVA).date()


def _utc(at: datetime) -> datetime:
    if at.tzinfo is None:
        raise ValueError("instants must be timezone-aware")
    return at.astimezone(UTC)
