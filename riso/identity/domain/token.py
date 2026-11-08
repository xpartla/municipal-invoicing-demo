"""Single-use tokens sent by mail (plan §5.3): an invitation (7 days), a password reset (1 hour)
and an email-change confirmation (24 hours, sent to the new address).

Like session tokens, only their SHA-256 is stored. A token works once, until it expires or a
newer one of the same kind replaces it. A failure never says which of these it was.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum

from riso.shared.errors import ValidationFailed
from riso.shared.events import DomainEvent


class TokenKind(StrEnum):
    INVITATION = "invitation"
    PASSWORD_RESET = "password_reset"
    EMAIL_CHANGE = "email_change"


LIFETIME: dict[TokenKind, timedelta] = {
    TokenKind.INVITATION: timedelta(days=7),
    TokenKind.PASSWORD_RESET: timedelta(hours=1),
    TokenKind.EMAIL_CHANGE: timedelta(hours=24),
}


def invalid_token() -> ValidationFailed:
    """The one answer for an unknown, used, replaced or expired token."""
    return ValidationFailed.on("token", "the link is not valid or has expired", "token_invalid")


@dataclass(slots=True)
class Token:
    id: str
    kind: TokenKind
    token_hash: str
    user_id: str
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None = None
    revoked_at: datetime | None = None
    payload: dict[str, str] = field(default_factory=dict)
    """For an email change, the new address."""
    events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def issue(
        cls,
        token_id: str,
        kind: TokenKind,
        token_hash: str,
        user_id: str,
        at: datetime,
        payload: dict[str, str] | None = None,
    ) -> "Token":
        return cls(
            id=token_id,
            kind=kind,
            token_hash=token_hash,
            user_id=user_id,
            created_at=at,
            expires_at=at + LIFETIME[kind],
            payload=dict(payload or {}),
        )

    def usable(self, now: datetime) -> bool:
        return self.used_at is None and self.revoked_at is None and now < self.expires_at

    def use(self, now: datetime) -> None:
        if not self.usable(now):
            raise invalid_token()
        self.used_at = now

    def revoke(self, now: datetime) -> None:
        """Replaced by a newer token of the same kind."""
        if self.used_at is None and self.revoked_at is None:
            self.revoked_at = now
