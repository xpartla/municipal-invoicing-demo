"""Sessions (expiry, touching, impersonation fields) and the login throttle."""

from datetime import UTC, datetime, timedelta

import pytest

from riso.identity.domain import (
    ABSOLUTE_LIMIT,
    IDLE_TIMEOUT,
    IMPERSONATION_LIMIT,
    LoginAttempts,
    Session,
    account_key,
    delay_after,
    hash_token,
    ip_key,
)
from riso.shared import InvalidState

T0 = datetime(2026, 6, 11, 8, 0, tzinfo=UTC)


def session() -> Session:
    return Session.start(
        "s1", hash_token("tok"), "csrf", "u1", T0, ip="127.0.0.1", user_agent="x" * 400
    )


def test_tokens_are_stored_as_their_sha256():
    assert hash_token("tok") == "1a7674eb4ee78df7e1ac439a93c3fa8e3c945784d4dec9fd8e3011738b2f1d62"
    assert len(hash_token("tok")) == 64 and hash_token("tok") != hash_token("tok2")


def test_a_new_session():
    s = session()
    assert (s.expires_at, s.idle_expires_at) == (T0 + ABSOLUTE_LIMIT, T0 + IDLE_TIMEOUT)
    assert len(s.user_agent) == 300
    assert s.is_valid(T0)
    assert s.principal_id == "u1"


def test_idle_and_absolute_expiry():
    s = session()
    assert s.is_valid(T0 + IDLE_TIMEOUT - timedelta(seconds=1))
    assert not s.is_valid(T0 + IDLE_TIMEOUT)
    for hours in range(6, 7 * 24, 6):
        assert s.touch(T0 + timedelta(hours=hours))
    assert s.is_valid(T0 + ABSOLUTE_LIMIT - timedelta(seconds=1))
    assert not s.is_valid(T0 + ABSOLUTE_LIMIT)


def test_touching_writes_once_a_minute():
    s = session()
    assert not s.touch(T0 + timedelta(seconds=59))
    assert s.last_seen_at == T0
    assert s.touch(T0 + timedelta(seconds=60))
    assert s.last_seen_at == T0 + timedelta(seconds=60)


def test_revoking():
    s = session()
    s.revoke(T0)
    assert not s.is_valid(T0)
    with pytest.raises(InvalidState):
        s.revoke(T0)


def test_impersonation_fields():
    s = session()
    with pytest.raises(InvalidState):
        s.start_impersonation("u1", "self", T0)
    s.start_impersonation("u2", "support ticket 42", T0)
    assert s.impersonating and s.principal_id == "u2"
    assert s.impersonation_expires_at == T0 + IMPERSONATION_LIMIT
    assert not s.impersonation_expired(T0 + IMPERSONATION_LIMIT - timedelta(seconds=1))
    assert s.impersonation_expired(T0 + IMPERSONATION_LIMIT)
    with pytest.raises(InvalidState):
        s.start_impersonation("u3", "again", T0)
    assert s.end_impersonation() == "u2"
    assert not s.impersonating and s.impersonation_expires_at is None
    with pytest.raises(InvalidState):
        s.end_impersonation()


@pytest.mark.parametrize(
    ("failures", "minutes"),
    [(0, 0), (4, 0), (5, 1), (6, 2), (7, 4), (8, 8), (9, 15), (20, 15)],
)
def test_the_delay_grows_to_fifteen_minutes(failures, minutes):
    assert delay_after(failures) == timedelta(minutes=minutes)


def test_a_counter_blocks_after_five_failures_and_forgets_after_a_day():
    attempts = LoginAttempts(account_key("Jana@Obec.sk"))
    for i in range(4):
        attempts.record_failure(T0 + timedelta(seconds=i))
        assert attempts.blocked_until(T0 + timedelta(seconds=i)) is None
    attempts.record_failure(T0 + timedelta(seconds=10))
    assert attempts.blocked_until(T0 + timedelta(seconds=10)) == T0 + timedelta(seconds=70)
    assert attempts.blocked_until(T0 + timedelta(seconds=70)) is None
    later = T0 + timedelta(days=1, seconds=10)
    attempts.record_failure(later)
    assert attempts.failures == 1  # the old ones were forgotten
    attempts.reset()
    assert (attempts.failures, attempts.last_failure_at) == (0, None)


def test_keys_are_hashed_and_normalised():
    assert account_key(" Jana@Obec.SK ") == account_key("jana@obec.sk")
    assert account_key("jana@obec.sk").startswith("account:")
    assert "obec" not in account_key("jana@obec.sk")
    assert ip_key("10.0.0.1").startswith("ip:") and "10.0" not in ip_key("10.0.0.1")
