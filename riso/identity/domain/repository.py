"""The repository protocols of the identity context."""

from collections.abc import Collection
from datetime import datetime
from typing import Protocol

from riso.identity.domain.email import Email
from riso.identity.domain.permissions import ScopeKind
from riso.identity.domain.session import Session
from riso.identity.domain.throttle import LoginAttempts
from riso.identity.domain.token import Token, TokenKind
from riso.identity.domain.user import User


class UserRepository(Protocol):
    def add(self, user: User) -> None: ...

    def get(self, user_id: str) -> User:
        """Raises `NotFound` when there is no such user (deleted and purged ones included)."""
        ...

    def find_by_email(self, email: Email) -> User | None:
        """The user whose login email this is, whatever its status."""
        ...

    def save(self, user: User) -> None:
        """Writes the user and its memberships."""
        ...

    def members_of_customer(self, customer_id: str) -> list[User]:
        """The users with a membership in the customer, active or not, by name."""
        ...

    def with_memberships_in(self, kind: ScopeKind, scope_ids: Collection[str]) -> list[User]:
        """The users with a membership in any of these customers or providers, by name."""
        ...

    def find(self, *, query: str | None = None, include_deleted: bool = False) -> list[User]:
        """Every user (not purged ones), by name; `query` matches the name or the email,
        ignoring case."""
        ...


class SessionRepository(Protocol):
    def add(self, session: Session) -> None: ...

    def by_token_hash(self, token_hash: str) -> Session | None: ...

    def get(self, session_id: str) -> Session:
        """Raises `NotFound`."""
        ...

    def save(self, session: Session) -> None: ...

    def active_of(self, user_id: str, now: datetime) -> list[Session]:
        """The user's sessions that are still valid at `now`, as the one who logged in
        (impersonation sessions of an admin are the admin's), newest first."""
        ...

    def impersonating(self, user_id: str) -> list[Session]:
        """The sessions, not ended, in which an admin acts as this user."""
        ...


class LoginAttemptRepository(Protocol):
    def get(self, key: str) -> LoginAttempts:
        """The key's counter; a fresh one when there is none."""
        ...

    def save(self, attempts: LoginAttempts) -> None: ...


class TokenRepository(Protocol):
    def add(self, token: Token) -> None: ...

    def by_hash(self, token_hash: str) -> Token | None: ...

    def save(self, token: Token) -> None: ...

    def outstanding(self, user_id: str, kind: TokenKind) -> list[Token]:
        """The user's tokens of this kind that were neither used nor revoked."""
        ...
