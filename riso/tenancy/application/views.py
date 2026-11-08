"""The views (DTOs) the tenancy use cases return."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from riso.tenancy.domain import (
    Address,
    Customer,
    CustomerParameters,
    CustomerStatus,
    ProviderStatus,
    ServiceProvider,
)


@dataclass(frozen=True, slots=True)
class AddressView:
    street: str
    city: str
    postal_code: str
    country: str

    @classmethod
    def of(cls, address: Address) -> "AddressView":
        return cls(address.street, address.city, address.postal_code, address.country)


@dataclass(frozen=True, slots=True)
class CustomerView:
    id: str
    name: str
    ico: str
    dic: str | None
    address: AddressView | None
    iban: str | None
    variable_number: str | None
    provider_id: str | None
    status: CustomerStatus
    created_at: datetime
    deleted_at: datetime | None

    @classmethod
    def of(cls, customer: Customer) -> "CustomerView":
        return cls(
            id=customer.id,
            name=customer.name,
            ico=customer.ico.value,
            dic=customer.dic,
            address=AddressView.of(customer.address) if customer.address else None,
            iban=customer.iban.value if customer.iban else None,
            variable_number=customer.variable_number,
            provider_id=customer.provider_id,
            status=customer.status,
            created_at=customer.created_at,
            deleted_at=customer.deleted_at,
        )


@dataclass(frozen=True, slots=True)
class ProviderView:
    id: str
    name: str
    ico: str | None
    status: ProviderStatus
    created_at: datetime
    removed_at: datetime | None

    @classmethod
    def of(cls, provider: ServiceProvider) -> "ProviderView":
        return cls(
            id=provider.id,
            name=provider.name,
            ico=provider.ico.value if provider.ico else None,
            status=provider.status,
            created_at=provider.created_at,
            removed_at=provider.removed_at,
        )


@dataclass(frozen=True, slots=True)
class ParametersView:
    customer_id: str
    year: int
    values: dict[str, Any]

    @classmethod
    def of(cls, parameters: CustomerParameters) -> "ParametersView":
        return cls(parameters.customer_id, parameters.year, parameters.values())
