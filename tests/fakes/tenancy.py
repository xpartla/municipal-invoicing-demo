"""In-memory repositories and the unit of work of the tenancy context."""

from riso.shared import NotFound
from riso.shared.values import Ico
from riso.tenancy.domain import Customer, CustomerParameters, ServiceProvider
from tests.fakes.memory import SnapshotStore, StoresUnitOfWork
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
        self.customers = self.store(InMemoryCustomers(self))
        self.providers = self.store(InMemoryProviders())
        self.parameters = self.store(InMemoryParameters())
