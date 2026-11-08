"""In-memory repositories and the unit of work of the tenancy context."""

from dataclasses import replace

from riso.shared import NotFound
from riso.shared.values import Ico
from riso.tenancy.application.ports import LoginRef
from riso.tenancy.domain import Customer, CustomerParameters, ServiceProvider
from tests.fakes.memory import SnapshotStore, StoresUnitOfWork
from tests.fakes.ports import RecordingAudit
from tests.fakes.uow import InMemoryUnitOfWork


class InMemoryCustomers(SnapshotStore):
    def __init__(self, uow: InMemoryUnitOfWork) -> None:
        super().__init__()
        self._uow = uow

    def add(self, customer: Customer) -> None:
        self.put(customer.id, customer)
        self._uow.track(customer)

    def get(self, customer_id: str) -> Customer:
        if customer_id not in self.rows:
            raise NotFound(f"no customer {customer_id}")
        customer = self.take(customer_id)
        self._uow.track(customer)
        return customer

    def find_active_by_ico(self, ico: Ico) -> Customer | None:
        found = [c for c in self.values() if c.ico == ico and c.active]
        return found[0] if found else None

    def save(self, customer: Customer) -> None:
        if customer.id not in self.rows:
            raise NotFound(f"no customer {customer.id}")
        self.put(customer.id, customer)

    def remove(self, customer_id: str) -> None:
        self.rows.pop(customer_id, None)

    def find(
        self, *, provider_id: str | None = None, include_deleted: bool = False
    ) -> list[Customer]:
        found = [
            c
            for c in self.values()
            if (include_deleted or c.active)
            and (provider_id is None or c.provider_id == provider_id)
        ]
        return sorted(found, key=lambda c: (c.name, c.id))

    def assigned_to(self, provider_id: str) -> list[Customer]:
        return [c for c in self.values() if c.provider_id == provider_id]


class InMemoryProviders(SnapshotStore):
    def add(self, provider: ServiceProvider) -> None:
        self.put(provider.id, provider)

    def get(self, provider_id: str) -> ServiceProvider:
        if provider_id not in self.rows:
            raise NotFound(f"no provider {provider_id}")
        return self.take(provider_id)

    def save(self, provider: ServiceProvider) -> None:
        self.put(provider.id, provider)

    def find(self, *, include_removed: bool = False) -> list[ServiceProvider]:
        return sorted(
            (p for p in self.values() if include_removed or p.active), key=lambda p: p.name
        )


class InMemoryParameters(SnapshotStore):
    def get(self, customer_id: str, year: int) -> CustomerParameters | None:
        return self.rows.get((customer_id, year))

    def save(self, parameters: CustomerParameters) -> None:
        self.put((parameters.customer_id, parameters.year), parameters)

    def years(self, customer_id: str) -> list[int]:
        return sorted(year for (cid, year) in self.rows if cid == customer_id)

    def remove_all(self, customer_id: str) -> None:
        for key in [k for k in self.rows if k[0] == customer_id]:
            del self.rows[key]


class InMemoryTenancyUnitOfWork(StoresUnitOfWork):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.audit = self.store(RecordingAudit())
        self.logins = FakeLogins()
        self.customers = self.store(InMemoryCustomers(self))
        self.providers = self.store(InMemoryProviders())
        self.parameters = self.store(InMemoryParameters())


class FakeLogins:
    """The `Logins` port over a plain list of (scope kind, scope ID, LoginRef)."""

    def __init__(self) -> None:
        self.rows: list[tuple[str, str, LoginRef]] = []

    def of_customers(self, customer_ids):
        return {c: [r for k, s, r in self.rows if k == "customer" and s == c] for c in customer_ids}

    def staff_of(self, provider_ids):
        return {
            p: [r for k, s, r in self.rows if k == "provider" and s == p and r.active]
            for p in provider_ids
        }

    def deactivate_staff(self, provider_id):
        count = 0
        for i, (k, s, r) in enumerate(self.rows):
            if k == "provider" and s == provider_id and r.active:
                self.rows[i] = (k, s, replace(r, active=False))
                count += 1
        return count

    def remove_customer_memberships(self, customer_id):
        before = len(self.rows)
        self.rows = [
            row for row in self.rows if not (row[0] == "customer" and row[1] == customer_id)
        ]
        return before - len(self.rows)
