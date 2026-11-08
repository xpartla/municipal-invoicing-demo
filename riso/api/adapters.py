"""Adapters between contexts, wired by the composition root."""

from collections.abc import Collection

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from riso.codelists import BundleEntity
from riso.identity.application.ports import CustomerRef, ProviderRef
from riso.identity.domain import MembershipScope, ScopeKind, UserStatus
from riso.identity.infrastructure.repository import SqlUserRepository
from riso.platform.db import Database
from riso.shared.clock import Clock
from riso.tenancy.application import CustomerView
from riso.tenancy.application.ports import LoginRef
from riso.tenancy.domain import CustomerStatus, ProviderStatus
from riso.tenancy.infrastructure.orm import (
    CustomerRow,
    ProviderAssignmentRow,
    ServiceProviderRow,
)


class SqlTenancyDirectory:
    """What identity needs to know about customers and providers (its `TenancyDirectory`
    port), read from the tenancy tables in short read-only sessions."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def customer(self, customer_id: str) -> CustomerRef | None:
        with self._db.session() as session:
            rows = self._customers(
                session, select(CustomerRow).where(CustomerRow.id == customer_id)
            )
        return rows[0] if rows else None

    def customers(
        self,
        *,
        ids: Collection[str] | None = None,
        provider_ids: Collection[str] | None = None,
    ) -> list[CustomerRef]:
        statement = select(CustomerRow).where(CustomerRow.status == CustomerStatus.ACTIVE.value)
        if ids is not None:
            statement = statement.where(CustomerRow.id.in_(list(ids)))
        if provider_ids is not None:
            statement = statement.join(
                ProviderAssignmentRow, ProviderAssignmentRow.customer_id == CustomerRow.id
            ).where(ProviderAssignmentRow.provider_id.in_(list(provider_ids)))
        with self._db.session() as session:
            return self._customers(session, statement.order_by(CustomerRow.name, CustomerRow.id))

    def provider(self, provider_id: str) -> ProviderRef | None:
        found = self.providers([provider_id])
        return found[0] if found else None

    def providers(self, ids: Collection[str]) -> list[ProviderRef]:
        if not ids:
            return []
        with self._db.session() as session:
            rows = session.scalars(
                select(ServiceProviderRow)
                .where(ServiceProviderRow.id.in_(list(ids)))
                .order_by(ServiceProviderRow.name, ServiceProviderRow.id)
            ).all()
            return [
                ProviderRef(row.id, row.name, row.status == ProviderStatus.ACTIVE.value)
                for row in rows
            ]

    @staticmethod
    def _customers(session: Session, statement: Select[CustomerRow]) -> list[CustomerRef]:
        rows = session.scalars(statement).all()
        if not rows:
            return []
        assignments = session.execute(
            select(ProviderAssignmentRow.customer_id, ProviderAssignmentRow.provider_id).where(
                ProviderAssignmentRow.customer_id.in_([r.id for r in rows])
            )
        )
        providers = {customer_id: provider_id for customer_id, provider_id in assignments}
        return [
            CustomerRef(
                id=row.id,
                name=row.name,
                ico=row.ico,
                provider_id=providers.get(row.id),
                active=row.status == CustomerStatus.ACTIVE.value,
            )
            for row in rows
        ]


class SpaLinks:
    """The SPA's pages that mail links to (`Links` port). Tokens go in the fragment."""

    def __init__(self, public_url: str) -> None:
        self._base = public_url.rstrip("/")

    def invitation(self, token: str) -> str:
        return f"{self._base}/invitation#{token}"

    def password_reset(self, token: str) -> str:
        return f"{self._base}/reset-password#{token}"

    def email_change(self, token: str) -> str:
        return f"{self._base}/confirm-email#{token}"

    def login(self) -> str:
        return f"{self._base}/login"


class UserLogins:
    """Tenancy's `Logins` port over identity's user repository, on the same session."""

    def __init__(self, users: SqlUserRepository, clock: Clock) -> None:
        self._users = users
        self._clock = clock

    def of_customers(self, customer_ids: Collection[str]) -> dict[str, list[LoginRef]]:
        return self._grouped(ScopeKind.CUSTOMER, customer_ids, active_only=False)

    def staff_of(self, provider_ids: Collection[str]) -> dict[str, list[LoginRef]]:
        return self._grouped(ScopeKind.PROVIDER, provider_ids, active_only=True)

    def _grouped(
        self, kind: ScopeKind, ids: Collection[str], *, active_only: bool
    ) -> dict[str, list[LoginRef]]:
        found: dict[str, list[LoginRef]] = {scope_id: [] for scope_id in ids}
        for user in self._users.with_memberships_in(kind, ids):
            if user.status in (UserStatus.DELETED, UserStatus.PURGED):
                continue
            for m in user.memberships:
                if m.scope.kind is kind and m.scope.id in found and (m.active or not active_only):
                    found[m.scope.id].append(
                        LoginRef(
                            user_id=user.id,
                            name=user.name,
                            email=user.email.value if user.email else None,
                            role=m.role.value,
                            active=m.active,
                            status=user.status.value,
                            locked=user.locked_at is not None,
                        )
                    )
        return found

    def deactivate_staff(self, provider_id: str) -> int:
        scope = MembershipScope.provider(provider_id)
        count = 0
        for user in self._users.with_memberships_in(ScopeKind.PROVIDER, [provider_id]):
            membership = user.membership_in(scope)
            if membership is not None and membership.active:
                membership.deactivate(self._clock.now())
                self._users.save(user)
                count += 1
        return count

    def remove_customer_memberships(self, customer_id: str) -> int:
        scope = MembershipScope.customer(customer_id)
        users = self._users.with_memberships_in(ScopeKind.CUSTOMER, [customer_id])
        for user in users:
            user.remove_membership(scope)
            self._users.save(user)
        return len(users)


def bundle_entity(customer: CustomerView) -> BundleEntity:
    """The customer as its reference bundle names it: the address on one line, the way the
    chart of accounts' title writes it ('Boldog 89, 925 26 Boldog')."""
    address = customer.address
    line = None
    if address is not None:
        postal = (
            f"{address.postal_code[:3]} {address.postal_code[3:]}"
            if address.country == "SK"
            else address.postal_code
        )
        line = f"{address.street}, {postal} {address.city}"
    return BundleEntity(ico=customer.ico, name=customer.name, address=line)
