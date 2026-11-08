"""Adapters between contexts, wired by the composition root."""

from collections.abc import Collection

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from riso.identity.application.ports import CustomerRef, ProviderRef
from riso.platform.db import Database
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
