"""Request and response models of the tenancy API."""

from datetime import datetime

from pydantic import BaseModel

from riso.tenancy.application import CustomerView, ProviderOverview, ProviderView
from riso.tenancy.domain import CustomerStatus, ProviderStatus


class AddressOut(BaseModel):
    street: str
    city: str
    postal_code: str
    country: str


class CustomerOut(BaseModel):
    id: str
    name: str
    ico: str
    dic: str | None
    address: AddressOut | None
    iban: str | None
    variable_number: str | None
    provider_id: str | None
    status: CustomerStatus
    created_at: datetime
    deleted_at: datetime | None

    @classmethod
    def of(cls, view: CustomerView) -> "CustomerOut":
        a = view.address
        return cls(
            id=view.id,
            name=view.name,
            ico=view.ico,
            dic=view.dic,
            address=AddressOut(
                street=a.street, city=a.city, postal_code=a.postal_code, country=a.country
            )
            if a
            else None,
            iban=view.iban,
            variable_number=view.variable_number,
            provider_id=view.provider_id,
            status=view.status,
            created_at=view.created_at,
            deleted_at=view.deleted_at,
        )


class ProviderOut(BaseModel):
    id: str
    name: str
    ico: str | None
    status: ProviderStatus
    created_at: datetime
    removed_at: datetime | None

    @classmethod
    def of(cls, view: ProviderView) -> "ProviderOut":
        return cls(
            id=view.id,
            name=view.name,
            ico=view.ico,
            status=view.status,
            created_at=view.created_at,
            removed_at=view.removed_at,
        )


class ProviderOverviewOut(BaseModel):
    provider: ProviderOut
    customers: list[CustomerOut]

    @classmethod
    def of(cls, view: ProviderOverview) -> "ProviderOverviewOut":
        return cls(
            provider=ProviderOut.of(view.provider),
            customers=[CustomerOut.of(c) for c in view.customers],
        )
