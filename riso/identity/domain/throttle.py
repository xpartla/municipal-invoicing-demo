"""Login throttling (plan §5.3).

Failed logins are counted per account (the typed email) and per client address. The first
five failures are free; from the fifth on, the key is blocked for 1 minute, then 2, 4, 8,
and at most 15 minutes after each further failure. Attempts while blocked are refused
without checking the password and are not counted. A success resets both keys; failures
are forgotten a day after the last one.

Keys are hashed (`account:<sha256>`, `ip:<sha256>`), so the table holds no typed addresses.
Locking an account is a separate admin action (`User.lock`).
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta

FREE_FAILURES = 5
FIRST_DELAY = timedelta(minutes=1)
MAX_DELAY = timedelta(minutes=15)
FORGET_AFTER = timedelta(days=1)


def account_key(email: str) -> str:
    return "account:" + hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def ip_key(ip: str) -> str:
    return "ip:" + hashlib.sha256(ip.encode("utf-8")).hexdigest()


def delay_after(failures: int) -> timedelta:
    """How long a key is blocked after its `failures`-th failure."""
    if failures < FREE_FAILURES:
        return timedelta(0)
    return min(MAX_DELAY, FIRST_DELAY * (1 << min(failures - FREE_FAILURES, 16)))


@dataclass(slots=True)
class LoginAttempts:
    key: str
    failures: int = 0
    last_failure_at: datetime | None = None

    def blocked_until(self, now: datetime) -> datetime | None:
        if self.last_failure_at is None or self.failures < FREE_FAILURES:
            return None
        if now - self.last_failure_at >= FORGET_AFTER:
            return None
        until = self.last_failure_at + delay_after(self.failures)
        return until if until > now else None

    def record_failure(self, now: datetime) -> None:
        if self.last_failure_at is not None and now - self.last_failure_at >= FORGET_AFTER:
            self.failures = 0
        self.failures += 1
        self.last_failure_at = now

    def reset(self) -> None:
        self.failures = 0
        self.last_failure_at = None
