"""In-memory repositories and the unit of work of the identity context."""

from collections.abc import Collection

from riso.identity.domain import Email, ScopeKind, User, UserStatus
from riso.shared import Conflict, NotFound
from tests.fakes.memory import SnapshotStore, StoresUnitOfWork
from tests.fakes.uow import InMemoryUnitOfWork


class InMemoryUsers(SnapshotStore):
    def __init__(self, uow: InMemoryUnitOfWork) -> None:
        super().__init__()
        self._uow = uow

    def _check_unique(self, user: User) -> None:
        if user.email is None:
            return
        for other in self.rows.values():
            if other.id != user.id and other.email == user.email:
                raise Conflict("email in use")  # the unique index of the SQL table

    def add(self, user: User) -> None:
        self._check_unique(user)
        self.put(user.id, user)
        self._uow.track(user)

    def get(self, user_id: str) -> User:
        if user_id not in self.rows:
            raise NotFound(f"no user {user_id}")
        user = self.take(user_id)
        self._uow.track(user)
        return user

    def find_by_email(self, email: Email) -> User | None:
        return next((u for u in self.values() if u.email == email), None)

    def save(self, user: User) -> None:
        if user.id not in self.rows:
            raise NotFound(f"no user {user.id}")
        self._check_unique(user)
        self.put(user.id, user)

    def members_of_customer(self, customer_id: str) -> list[User]:
        return self.with_memberships_in(ScopeKind.CUSTOMER, [customer_id])

    def with_memberships_in(self, kind: ScopeKind, scope_ids: Collection[str]) -> list[User]:
        found = [
            u
            for u in self.values()
            if any(m.scope.kind is kind and m.scope.id in scope_ids for m in u.memberships)
        ]
        return sorted(found, key=lambda u: (u.name, u.id))

    def find(self, *, query: str | None = None, include_deleted: bool = False) -> list[User]:
        folded = (query or "").strip().lower()
        found = [
            u
            for u in self.values()
            if u.status is not UserStatus.PURGED
            and (include_deleted or u.status is not UserStatus.DELETED)
            and (
                not folded
                or folded in u.name.lower()
                or folded in (u.email.value if u.email else "")
            )
        ]
        return sorted(found, key=lambda u: (u.name, u.id))


class InMemoryIdentityUnitOfWork(StoresUnitOfWork):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.users = self.store(InMemoryUsers(self))
