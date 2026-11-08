"""The `Customer` aggregate: an accounting entity with an IČO, e.g. Obec Boldog (plan §3, §5.5,
§5.6).

    active ──delete──> deleted ──restore──> active
                          └──purge (the IČO typed to confirm)──> gone

A customer has at most one service provider (plan §2 decision 4); moving it to another one
means unassigning it first. The IČO is unique among active customers; the application
service checks that, since it needs the repository.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from riso.shared.errors import Conflict, InvalidState, ValidationFailed
from riso.shared.events import DomainEvent
from riso.shared.values import Iban, Ico, clean_name
from riso.tenancy.domain.provider import ServiceProvider

_DIC = re.compile(r"[1-9]\d{9}")
_VARIABLE_NUMBER = re.compile(r"\d{1,10}")
_SK_POSTAL_CODE = re.compile(r"\d{5}")
_POSTAL_CODE = re.compile(r"[A-Z0-9][A-Z0-9 -]{1,9}")


def parse_dic(text: str, field: str = "dic") -> str:
    """A Slovak DIČ: ten digits, the first not zero. Spaces are dropped."""
    compact = "".join(text.split())
    if not _DIC.fullmatch(compact):
        raise ValidationFailed.on(field, "not a valid DIČ (ten digits)", "dic")
    return compact


def parse_variable_number(text: str, field: str = "variable_number") -> str:
    """A variable symbol: one to ten digits."""
    compact = "".join(text.split())
    if not _VARIABLE_NUMBER.fullmatch(compact):
        raise ValidationFailed.on(field, "one to ten digits", "variable_number")
    return compact


@dataclass(frozen=True, slots=True)
class Address:
    street: str
    """Street and number, or the village and number where there are no streets."""
    city: str
    postal_code: str
    """Five digits for Slovakia, kept without the space (shown as `925 28`)."""
    country: str = "SK"

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Z]{2}", self.country):
            raise ValidationFailed.on("address.country", "not an ISO 3166 code", "country")
        pattern = _SK_POSTAL_CODE if self.country == "SK" else _POSTAL_CODE
        if not pattern.fullmatch(self.postal_code):
            raise ValidationFailed.on("address.postal_code", "not a postal code", "postal_code")

    @classmethod
    def parse(cls, street: str, city: str, postal_code: str, country: str = "SK") -> "Address":
        country = country.strip().upper()
        code = postal_code.strip().upper()
        if country == "SK":
            code = "".join(code.split())
        return cls(
            street=clean_name(street, "address.street"),
            city=clean_name(city, "address.city", max_length=100),
            postal_code=code,
            country=country,
        )

    @property
    def formatted_postal_code(self) -> str:
        if self.country == "SK":
            return f"{self.postal_code[:3]} {self.postal_code[3:]}"
        return self.postal_code


class CustomerStatus(StrEnum):
    ACTIVE = "active"
    DELETED = "deleted"


@dataclass(slots=True)
class Customer:
    id: str
    name: str
    ico: Ico
    created_at: datetime
    dic: str | None = None
    address: Address | None = None
    iban: Iban | None = None
    variable_number: str | None = None
    """Assigned by staff or the admin; read-only for the customer's users (decision 34)."""
    provider_id: str | None = None
    status: CustomerStatus = CustomerStatus.ACTIVE
    deleted_at: datetime | None = None
    events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def create(
        cls,
        customer_id: str,
        name: str,
        ico: Ico,
        at: datetime,
        *,
        dic: str | None = None,
        address: Address | None = None,
        iban: Iban | None = None,
    ) -> "Customer":
        return cls(
            id=customer_id,
            name=clean_name(name),
            ico=ico,
            created_at=at,
            dic=dic,
            address=address,
            iban=iban,
        )

    @property
    def active(self) -> bool:
        return self.status is CustomerStatus.ACTIVE

    def _require_active(self) -> None:
        if not self.active:
            raise InvalidState(f"customer {self.id} is {self.status}")

    def update_identity(self, name: str, ico: Ico, dic: str | None) -> None:
        """Name, IČO and DIČ: staff and admins only (plan §2 decision 50)."""
        self._require_active()
        self.name = clean_name(name)
        self.ico = ico
        self.dic = dic

    def update_contact(self, address: Address | None, iban: Iban | None) -> None:
        self._require_active()
        self.address = address
        self.iban = iban

    def assign_variable_number(self, variable_number: str | None) -> None:
        self._require_active()
        self.variable_number = variable_number

    def assign_to(self, provider: ServiceProvider) -> None:
        """Assigns the customer to a provider. It has at most one, so a customer assigned
        elsewhere is a conflict: unassign it first."""
        self._require_active()
        if not provider.active:
            raise InvalidState(f"provider {provider.id} is removed")
        if self.provider_id == provider.id:
            raise InvalidState(f"customer {self.id} is already assigned to {provider.id}")
        if self.provider_id is not None:
            raise Conflict(f"customer {self.id} is assigned to another provider")
        self.provider_id = provider.id

    def unassign(self) -> None:
        if self.provider_id is None:
            raise InvalidState(f"customer {self.id} has no provider")
        self.provider_id = None

    def delete(self, at: datetime) -> None:
        """Soft delete: the customer is hidden from everyone but admins, and restorable."""
        self._require_active()
        self.status = CustomerStatus.DELETED
        self.deleted_at = at

    def restore(self) -> None:
        if self.status is not CustomerStatus.DELETED:
            raise InvalidState(f"customer {self.id} is not deleted")
        self.status = CustomerStatus.ACTIVE
        self.deleted_at = None

    def confirm_purge(self, typed_ico: str) -> None:
        """The precondition of a purge: the customer is deleted, and the IČO was typed to
        confirm (plan §5.6). Raises; the purge itself is the application's (it removes rows
        of several contexts)."""
        if self.status is not CustomerStatus.DELETED:
            raise InvalidState(f"customer {self.id} must be deleted before it is purged")
        if "".join(typed_ico.split()) != self.ico.value:
            raise ValidationFailed.on("ico_confirmation", "the IČO does not match", "mismatch")
