"""The user repository on SQLAlchemy: users and their memberships, mapped explicitly."""

from collections.abc import Collection

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from riso.identity.domain import (
    Email,
    Membership,
    MembershipScope,
    Role,
    ScopeKind,
    User,
    UserStatus,
)
from riso.identity.infrastructure.orm import MembershipRow, UserRow
from riso.shared.errors import NotFound
from riso.shared.uow import UnitOfWork


class SqlUserRepository:
    def __init__(self, session: Session, uow: UnitOfWork) -> None:
        self._session = session
        self._uow = uow

    def add(self, user: User) -> None:
        row = UserRow(id=user.id)
        _write(user, row)
        self._session.add(row)
        self._sync_memberships(user)
        self._uow.track(user)

    def get(self, user_id: str) -> User:
        row = self._session.get(UserRow, user_id)
        if row is None:
            raise NotFound(f"no user {user_id}")
        return self._read([row])[0]

    def find_by_email(self, email: Email) -> User | None:
        row = self._session.scalars(select(UserRow).where(UserRow.email == email.value)).first()
        return None if row is None else self._read([row])[0]

    def save(self, user: User) -> None:
        row = self._session.get(UserRow, user.id)
        if row is None:
            raise NotFound(f"no user {user.id}")
        _write(user, row)
        self._sync_memberships(user)

    def members_of_customer(self, customer_id: str) -> list[User]:
        return self.with_memberships_in(ScopeKind.CUSTOMER, [customer_id])

    def with_memberships_in(self, kind: ScopeKind, scope_ids: Collection[str]) -> list[User]:
        if not scope_ids:
            return []
        ids = select(MembershipRow.user_id).where(
            MembershipRow.scope_kind == kind.value, MembershipRow.scope_id.in_(list(scope_ids))
        )
        rows = self._session.scalars(
            select(UserRow).where(UserRow.id.in_(ids)).order_by(UserRow.name, UserRow.id)
        ).all()
        return self._read(list(rows))

    def find(self, *, query: str | None = None, include_deleted: bool = False) -> list[User]:
        statement = select(UserRow).where(UserRow.status != UserStatus.PURGED.value)
        if not include_deleted:
            statement = statement.where(UserRow.status != UserStatus.DELETED.value)
        if query:
            folded = query.strip().lower()
            statement = statement.where(
                or_(
                    func.lower(UserRow.name).contains(folded, autoescape=True),
                    UserRow.email.contains(folded, autoescape=True),
                )
            )
        rows = self._session.scalars(statement.order_by(UserRow.name, UserRow.id)).all()
        return self._read(list(rows))

    # Mapping -----------------------------------------------------------------------------

    def _read(self, rows: list[UserRow]) -> list[User]:
        """Users with their memberships, in the order of `rows`; each one tracked."""
        memberships: dict[str, list[Membership]] = {row.id: [] for row in rows}
        if rows:
            found = self._session.scalars(
                select(MembershipRow)
                .where(MembershipRow.user_id.in_(list(memberships)))
                .order_by(MembershipRow.created_at, MembershipRow.id)
            ).all()
            for m in found:
                memberships[m.user_id].append(
                    Membership(
                        id=m.id,
                        scope=MembershipScope(ScopeKind(m.scope_kind), m.scope_id),
                        role=Role(m.role),
                        created_at=m.created_at,
                        deactivated_at=m.deactivated_at,
                    )
                )
        users = [_user(row, memberships[row.id]) for row in rows]
        for user in users:
            self._uow.track(user)
        return users

    def _sync_memberships(self, user: User) -> None:
        """Makes the rows equal the user's memberships: updates, adds and deletes by ID."""
        rows = {
            row.id: row
            for row in self._session.scalars(
                select(MembershipRow).where(MembershipRow.user_id == user.id)
            )
        }
        kept = {m.id for m in user.memberships}
        gone = [membership_id for membership_id in rows if membership_id not in kept]
        if gone:
            self._session.execute(delete(MembershipRow).where(MembershipRow.id.in_(gone)))
        for membership in user.memberships:
            row = rows.get(membership.id)
            if row is None:
                row = MembershipRow(id=membership.id, user_id=user.id)
                self._session.add(row)
            row.scope_kind = membership.scope.kind.value
            row.scope_id = membership.scope.id
            row.role = membership.role.value
            row.created_at = membership.created_at
            row.deactivated_at = membership.deactivated_at


def _write(user: User, row: UserRow) -> None:
    row.name = user.name
    row.email = user.email.value if user.email else None
    row.notification_email = user.notification_email.value if user.notification_email else None
    row.password_hash = user.password_hash
    row.status = user.status.value
    row.created_at = user.created_at
    row.password_changed_at = user.password_changed_at
    row.locked_at = user.locked_at
    row.deleted_at = user.deleted_at
    row.purged_at = user.purged_at


def _user(row: UserRow, memberships: list[Membership]) -> User:
    return User(
        id=row.id,
        name=row.name,
        email=Email(row.email) if row.email else None,
        created_at=row.created_at,
        status=UserStatus(row.status),
        notification_email=Email(row.notification_email) if row.notification_email else None,
        password_hash=row.password_hash,
        password_changed_at=row.password_changed_at,
        locked_at=row.locked_at,
        deleted_at=row.deleted_at,
        purged_at=row.purged_at,
        memberships=memberships,
    )
