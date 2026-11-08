"""A login session (plan §5.3).

The browser holds a random token in the `riso_session` cookie; the server keeps only its
SHA-256. A session ends when it is revoked (logout, "log out everywhere", a password change,
an admin's forced logout, locking or deleting the user), after 8 hours without a request,
or 7 days after the login, whichever comes first.

Each session has its own CSRF token, which the browser sends back in the `X-CSRF-Token`
header on every unsafe request (a double submit, checked against this copy).

The time of the last request is written at most once a minute, so most requests only read.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from riso.shared.errors import InvalidState
from riso.shared.events import DomainEvent

IDLE_TIMEOUT = timedelta(hours=8)
ABSOLUTE_LIMIT = timedelta(days=7)
TOUCH_INTERVAL = timedelta(minutes=1)
IMPERSONATION_LIMIT = timedelta(minutes=60)


def hash_token(token: str) -> str:
    """How tokens are stored: the hex SHA-256 of the token's text. Tokens are 256 random bits,
    so a plain hash is enough; no salt or stretching is needed."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class Session:
    id: str
    token_hash: str
    user_id: str
    """Who logged in. When an admin impersonates someone, this stays the admin."""
    csrf_token: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    """The absolute limit."""
    ip: str | None = None
    user_agent: str | None = None
    revoked_at: datetime | None = None
    impersonated_user_id: str | None = None
    impersonation_reason: str | None = None
    impersonation_started_at: datetime | None = None
    events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def start(
        cls,
        session_id: str,
        token_hash: str,
        csrf_token: str,
        user_id: str,
        at: datetime,
        *,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> "Session":
        return cls(
            id=session_id,
            token_hash=token_hash,
            user_id=user_id,
            csrf_token=csrf_token,
            created_at=at,
            last_seen_at=at,
            expires_at=at + ABSOLUTE_LIMIT,
            ip=ip,
            user_agent=(user_agent or "")[:300] or None,
        )

    @property
    def idle_expires_at(self) -> datetime:
        return self.last_seen_at + IDLE_TIMEOUT

    def is_valid(self, now: datetime) -> bool:
        return self.revoked_at is None and now < self.expires_at and now < self.idle_expires_at

    def touch(self, now: datetime) -> bool:
        """Records a request; True when the time was written (once a minute at most)."""
        if now - self.last_seen_at < TOUCH_INTERVAL:
            return False
        self.last_seen_at = now
        return True

    def revoke(self, at: datetime) -> None:
        if self.revoked_at is not None:
            raise InvalidState(f"session {self.id} is already ended")
        self.revoked_at = at

    # Impersonation (plan §5.4) ----------------------------------------------------------

    @property
    def impersonating(self) -> bool:
        return self.impersonated_user_id is not None

    @property
    def principal_id(self) -> str:
        """Whom the requests act as: the impersonated user, else the one who logged in."""
        return self.impersonated_user_id or self.user_id

    @property
    def impersonation_expires_at(self) -> datetime | None:
        if self.impersonation_started_at is None:
            return None
        return self.impersonation_started_at + IMPERSONATION_LIMIT

    def impersonation_expired(self, now: datetime) -> bool:
        expires = self.impersonation_expires_at
        return expires is not None and now >= expires

    def start_impersonation(self, user_id: str, reason: str, at: datetime) -> None:
        if self.impersonating:
            raise InvalidState(f"session {self.id} already impersonates someone")
        if user_id == self.user_id:
            raise InvalidState("one cannot impersonate oneself")
        self.impersonated_user_id = user_id
        self.impersonation_reason = reason
        self.impersonation_started_at = at

    def end_impersonation(self) -> str:
        """Ends it and returns the user who was impersonated."""
        if self.impersonated_user_id is None:
            raise InvalidState(f"session {self.id} impersonates nobody")
        user_id = self.impersonated_user_id
        self.impersonated_user_id = None
        self.impersonation_reason = None
        self.impersonation_started_at = None
        return user_id
