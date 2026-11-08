"""Request and response models of the tenancy API."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from riso.tenancy.application import (
    CustomerView,
    CustomerWithLogins,
    LoginRef,
    ParametersView,
    ProviderDetail,
    ProviderOverview,
    ProviderView,
)
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


class AddressIn(BaseModel):
    street: str = Field(max_length=200)
    city: str = Field(max_length=100)
    postal_code: str = Field(max_length=12)
    country: str = Field(default="SK", max_length=2)


class CustomerContactIn(BaseModel):
    address: AddressIn | None = None
    iban: str | None = Field(default=None, max_length=42)


class CustomerIdentityIn(BaseModel):
    name: str = Field(max_length=200)
    ico: str = Field(max_length=12)
    dic: str | None = Field(default=None, max_length=14)


class CustomerIn(CustomerIdentityIn, CustomerContactIn):
    pass


class AdminCustomerIn(CustomerIn):
    provider_id: str | None = Field(default=None, max_length=36)


class VariableNumberIn(BaseModel):
    variable_number: str | None = Field(default=None, max_length=14)


class PurgeIn(BaseModel):
    ico_confirmation: str = Field(max_length=12)


class ProviderIn(BaseModel):
    name: str = Field(max_length=200)
    ico: str | None = Field(default=None, max_length=12)


class AssignProviderIn(BaseModel):
    provider_id: str = Field(max_length=36)


class LoginOut(BaseModel):
    user_id: str
    name: str
    email: str | None
    role: str
    active: bool
    status: str
    locked: bool

    @classmethod
    def of(cls, ref: LoginRef) -> "LoginOut":
        return cls(
            user_id=ref.user_id,
            name=ref.name,
            email=ref.email,
            role=ref.role,
            active=ref.active,
            status=ref.status,
            locked=ref.locked,
        )


class CustomerWithLoginsOut(BaseModel):
    customer: CustomerOut
    logins: list[LoginOut]

    @classmethod
    def of(cls, view: CustomerWithLogins) -> "CustomerWithLoginsOut":
        return cls(
            customer=CustomerOut.of(view.customer), logins=[LoginOut.of(x) for x in view.logins]
        )


class ProviderDetailOut(BaseModel):
    provider: ProviderOut
    staff: list[LoginOut]
    customers: list[CustomerOut]

    @classmethod
    def of(cls, view: ProviderDetail) -> "ProviderDetailOut":
        return cls(
            provider=ProviderOut.of(view.provider),
            staff=[LoginOut.of(x) for x in view.staff],
            customers=[CustomerOut.of(c) for c in view.customers],
        )


class ParametersOut(BaseModel):
    customer_id: str
    year: int
    values: dict[str, Any] = Field(
        description="vat_payer, default_zdroj, default_series, default_dal, canteen_series, "
        "canteen_dal"
    )

    @classmethod
    def of(cls, view: ParametersView) -> "ParametersOut":
        return cls(customer_id=view.customer_id, year=view.year, values=view.values)


class ParametersIn(BaseModel):
    values: dict[str, Any]
