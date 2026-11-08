"""The repository protocols of the tenancy context. Every method on a customer's data takes
the customer's ID (guide §6.4)."""

from typing import Protocol

from riso.shared.values import Ico
from riso.tenancy.domain.customer import Customer
from riso.tenancy.domain.parameters import CustomerParameters
from riso.tenancy.domain.provider import ServiceProvider


class CustomerRepository(Protocol):
    def add(self, customer: Customer) -> None: ...

    def get(self, customer_id: str) -> Customer:
        """Raises `NotFound` when there is no such customer (deleted ones included)."""
        ...

    def find_active_by_ico(self, ico: Ico) -> Customer | None: ...

    def save(self, customer: Customer) -> None: ...

    def remove(self, customer_id: str) -> None:
        """Deletes the row for good (a purge)."""
        ...

    def find(
        self, *, provider_id: str | None = None, include_deleted: bool = False
    ) -> list[Customer]:
        """Customers by name; only the provider's when `provider_id` is given."""
        ...

    def assigned_to(self, provider_id: str) -> list[Customer]:
        """Every customer assigned to the provider, deleted ones included."""
        ...


class ProviderRepository(Protocol):
    def add(self, provider: ServiceProvider) -> None: ...

    def get(self, provider_id: str) -> ServiceProvider:
        """Raises `NotFound` when there is no such provider (removed ones included)."""
        ...

    def save(self, provider: ServiceProvider) -> None: ...

    def find(self, *, include_removed: bool = False) -> list[ServiceProvider]: ...


class ParametersRepository(Protocol):
    def get(self, customer_id: str, year: int) -> CustomerParameters | None: ...

    def save(self, parameters: CustomerParameters) -> None:
        """Adds or replaces the customer's parameters for the year."""
        ...

    def years(self, customer_id: str) -> list[int]: ...

    def remove_all(self, customer_id: str) -> None: ...
