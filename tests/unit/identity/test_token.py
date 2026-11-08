"""Mail tokens: lifetimes, single use, replacement."""

from datetime import UTC, datetime, timedelta

import pytest

from riso.identity.domain import LIFETIME, Token, TokenKind, hash_token
from riso.shared import ValidationFailed

T0 = datetime(2026, 6, 11, 8, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("kind", "lifetime"),
    [
        (TokenKind.INVITATION, timedelta(days=7)),
        (TokenKind.PASSWORD_RESET, timedelta(hours=1)),
        (TokenKind.EMAIL_CHANGE, timedelta(hours=24)),
    ],
)
def test_lifetimes(kind, lifetime):
    assert LIFETIME[kind] == lifetime
    token = Token.issue("t1", kind, hash_token("s"), "u1", T0)
    assert token.usable(T0 + lifetime - timedelta(seconds=1))
    assert not token.usable(T0 + lifetime)


def test_a_token_works_once():
    token = Token.issue("t1", TokenKind.PASSWORD_RESET, hash_token("s"), "u1", T0)
    token.use(T0)
    assert token.used_at == T0
    with pytest.raises(ValidationFailed) as caught:
        token.use(T0)
    assert caught.value.errors[0].code == "token_invalid"


def test_a_replaced_token_stops_working_and_keeps_its_use():
    token = Token.issue("t1", TokenKind.INVITATION, hash_token("s"), "u1", T0, {"x": "y"})
    token.revoke(T0)
    assert not token.usable(T0) and token.revoked_at == T0
    used = Token.issue("t2", TokenKind.INVITATION, hash_token("s2"), "u1", T0)
    used.use(T0)
    used.revoke(T0 + timedelta(minutes=1))
    assert used.revoked_at is None  # a used token stays used, not revoked
    assert token.payload == {"x": "y"}
