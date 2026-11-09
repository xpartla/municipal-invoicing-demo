"""Adapters between contexts, wired by the composition root."""

from collections.abc import Callable, Collection
from typing import TYPE_CHECKING

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from riso.codelists import BundleEntity, active_entries, customer_knowledge, reference_bundle
from riso.contracts import Counters, EntityContext, ReferenceBundle, SupplierMemory
from riso.exchange.domain.bookings import BookingsPlan
from riso.identity.application.ports import CustomerRef, ProviderRef
from riso.identity.domain import MembershipScope, ScopeKind, UserStatus
from riso.identity.infrastructure.repository import SqlUserRepository
from riso.invoicing import (
    PastPrecedent,
    add_past_bookings,
    copy_memory,
    counters,
    supplier_memory,
)
from riso.knowledge import KnowledgeBase
from riso.platform.db import Database
from riso.reference import UnknownEntity
from riso.shared.clock import Clock
from riso.shared.context import RequestContext
from riso.shared.errors import InvalidState, NotFound
from riso.shared.values import Ico
from riso.tenancy.application import CustomerView, get_customer, get_parameters
from riso.tenancy.application.ports import LoginRef
from riso.tenancy.domain import CustomerStatus, ProviderStatus

if TYPE_CHECKING:
    from riso.api.uow import AppUnitOfWork

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


class DbReferenceData:
    """The invoicing context's `ReferenceData` from the database: the customer and its
    parameters (tenancy), the bundle of its active code lists and its merged knowledge
    (codelists). Each call runs its own read-only unit of work."""

    def __init__(self, uow: Callable[[], "AppUnitOfWork"]) -> None:
        self._uow = uow

    def _customer(self, ctx: RequestContext, customer_id: str) -> CustomerView:
        return get_customer(ctx, self._uow(), customer_id)

    def bundle(self, ctx: RequestContext, customer_id: str, year: int) -> ReferenceBundle:
        entity = bundle_entity(self._customer(ctx, customer_id))
        return reference_bundle(ctx, self._uow(), customer_id, year, entity)

    def entity_context(self, ctx: RequestContext, customer_id: str, year: int) -> EntityContext:
        customer = self._customer(ctx, customer_id)
        try:
            parameters = get_parameters(ctx, self._uow(), customer_id, year)
        except NotFound as exc:
            raise InvalidState(f"customer {customer_id} has no parameters for {year}") from exc
        period = self.bundle(ctx, customer_id, year).period
        return EntityContext.model_validate(
            {
                "ico": customer.ico,
                "name": customer.name,
                "budget_year": year,
                "reference_period": period,
                **parameters.values,
            }
        )

    def knowledge(self, ctx: RequestContext, customer_id: str, year: int) -> KnowledgeBase:
        return customer_knowledge(ctx, self._uow(), customer_id, year)[0]

    def basis(
        self, ctx: RequestContext, customer_id: str, year: int
    ) -> tuple[tuple[str, ...], int]:
        revision = customer_knowledge(ctx, self._uow(), customer_id, year)[1]
        with self._uow() as uow:
            versions = uow.codelists.active_ids(customer_id, year)
        return tuple(sorted(versions.values())), revision


def _ico(uow: "AppUnitOfWork", customer_id: str) -> str:
    return uow.customers.get(customer_id).ico.value


class CodelistSeriesPatterns:
    """The invoicing context's `SeriesPatterns`: the active document series list of the
    year, in the same unit of work."""

    def __init__(self, uow: "AppUnitOfWork") -> None:
        self._uow = uow

    def patterns(self, customer_id: str, year: int) -> dict[str, str]:
        return {
            str(e.values["code"]): str(e.values["pattern"])
            for e in active_entries(self._uow, customer_id, "document_series", year)
        }

    def invoice_series(self, customer_id: str, year: int) -> tuple[str, ...]:
        parameters = self._uow.parameters.get(customer_id, year)
        if parameters is None:
            return ()
        values = parameters.values()
        return tuple(dict.fromkeys((values["default_series"], values["canteen_series"])))


class UowPrecedents:
    """The exchange context's `PrecedentSink` on the database (P2-M4-T02): the supplier
    memory and number series of the invoicing context, in the import's or the copy's own
    unit of work, so they commit with it."""

    def __init__(self, uow: "AppUnitOfWork") -> None:
        self._uow = uow

    def memory(self, customer_id: str) -> SupplierMemory:
        return supplier_memory(self._uow, customer_id, _ico(self._uow, customer_id))

    def counters(self, customer_id: str) -> Counters:
        return counters(self._uow, customer_id, _ico(self._uow, customer_id))

    def add(self, customer_id: str, plan: BookingsPlan) -> None:
        add_past_bookings(
            self._uow,
            customer_id,
            [PastPrecedent(b.supplier_ico, b.supplier_name, b.precedent) for b in plan.new],
            plan.numbers,
            {rise.key: rise.after for rise in plan.counters},
            plan.patterns,
        )

    def copy_memory(self, source_id: str, target_id: str) -> int:
        return copy_memory(self._uow, source_id, target_id)


class DbSupplierState:
    """The engine's supplier memory and counters for a stateless coding (the invoicing
    context's `SupplierState`), each read in its own read-only unit of work."""

    def __init__(self, uow: Callable[[], "AppUnitOfWork"]) -> None:
        self._uow = uow

    def memory(self, customer_id: str) -> SupplierMemory:
        with self._uow() as uow:
            return supplier_memory(uow, customer_id, _ico(uow, customer_id))

    def counters(self, customer_id: str) -> Counters:
        with self._uow() as uow:
            return counters(uow, customer_id, _ico(uow, customer_id))


class DatabaseReferenceSource:
    """The evaluation's `ReferenceSource` on the database (`riso eval --source db`): the
    active customer with the IČO, its parameters of its newest year, the bundle of its active
    code lists for that year, and its merged knowledge. The memory stays the evaluation's
    own (data/initial_state), never the database's."""

    def __init__(
        self, uow: Callable[[], "AppUnitOfWork"], reference: DbReferenceData, ctx: RequestContext
    ) -> None:
        self._uow = uow
        self._reference = reference
        self._ctx = ctx

    def _customer(self, ico: str) -> tuple[str, int]:
        with self._uow() as uow:
            customer = uow.customers.find_active_by_ico(Ico(ico))
            years = uow.parameters.years(customer.id) if customer else []
        if customer is None or not years:
            raise UnknownEntity(f"no customer with parameters for IČO {ico} in the database")
        return customer.id, years[-1]

    def entities(self) -> list[str]:
        with self._uow() as uow:
            return sorted(c.ico.value for c in uow.customers.find())

    def context(self, ico: str) -> EntityContext:
        customer_id, year = self._customer(ico)
        return self._reference.entity_context(self._ctx, customer_id, year)

    def bundle(self, ico: str, period: str | None = None) -> ReferenceBundle:
        customer_id, year = self._customer(ico)
        bundle = self._reference.bundle(self._ctx, customer_id, year)
        if period is not None and period != bundle.period:
            raise UnknownEntity(f"the database's lists for {ico} are of {bundle.period}")
        return bundle

    def knowledge(self, ico: str, year: int) -> KnowledgeBase:
        customer_id, _ = self._customer(ico)
        return self._reference.knowledge(self._ctx, customer_id, year)
