"""The repository protocols of the identity context."""

from collections.abc import Collection
from typing import Protocol

from riso.identity.domain.email import Email
from riso.identity.domain.permissions import ScopeKind
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
