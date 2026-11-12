"""Customer use cases: creating, reading and editing a customer, deleting and restoring it, and
its parameters (plan §5.5, §5.6, §6.4).

The IČO is unique among active customers, which needs the repository, so the use cases
check it: on create, on an IČO change, and on restore.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from riso.identity import Permission
from riso.shared.context import RequestContext
from riso.shared.errors import Conflict, FieldErrors, NotFound
from riso.shared.ports import AuditRecorder
from riso.shared.uow import UnitOfWork
from riso.shared.values import Iban, Ico, clean_name
from riso.tenancy.application.ports import Logins
from riso.tenancy.application.views import CustomerView, ParametersView
from riso.tenancy.domain import (
    Address,
    Customer,
    CustomerParameters,
    CustomerRepository,
    ParametersRepository,
    ProviderRepository,
    parse_dic,
    parse_variable_number,
)


class TenancyUnitOfWork(UnitOfWork, Protocol):
    @property
    def customers(self) -> CustomerRepository: ...

    @property
    def providers(self) -> ProviderRepository: ...

    @property
    def parameters(self) -> ParametersRepository: ...

    @property
    def audit(self) -> AuditRecorder: ...

    @property
    def logins(self) -> Logins: ...


def _audit(
    ctx: RequestContext,
    uow: TenancyUnitOfWork,
    action: str,
    customer_id: str,
    details: dict[str, object] | None = None,
) -> None:
    uow.audit.record(
        ctx,
        action,
        target_type="customer",
        target_id=customer_id,
        customer_id=customer_id,
        details=details,
    )


@dataclass(frozen=True, slots=True)
class AddressInput:
    street: str
    city: str
    postal_code: str
    country: str = "SK"


@dataclass(frozen=True, slots=True)
class CustomerIdentity:
    name: str
    ico: str
    dic: str | None = None


@dataclass(frozen=True, slots=True)
class CustomerContact:
    address: AddressInput | None = None
    iban: str | None = None


@dataclass(frozen=True, slots=True)
class CreateCustomer:
    identity: CustomerIdentity
    contact: CustomerContact = CustomerContact()
    provider_id: str | None = None
    """Staff create customers in their own provider; an admin may leave it empty."""


@dataclass(frozen=True, slots=True)
class _Identity:
    name: str
    ico: Ico
    dic: str | None


def _parse_identity(identity: CustomerIdentity, errors: FieldErrors) -> _Identity | None:
    """The parsed identity, or None with the failures added to `errors`."""
    name = errors.check(lambda: clean_name(identity.name))
    ico = errors.check(lambda: Ico.parse(identity.ico))
    typed_dic = identity.dic
    dic = errors.check(lambda: parse_dic(typed_dic)) if typed_dic else None
    if name is None or ico is None:
        return None
    return _Identity(name, ico, dic)


def _parse_contact(
    contact: CustomerContact, errors: FieldErrors
) -> tuple[Address | None, Iban | None]:
    given = contact.address
    address = (
        errors.check(
            lambda: Address.parse(given.street, given.city, given.postal_code, given.country)
        )
        if given is not None
        else None
    )
    typed_iban = contact.iban
    iban = errors.check(lambda: Iban.parse(typed_iban)) if typed_iban else None
    return address, iban


def _require_unique_ico(uow: TenancyUnitOfWork, ico: Ico, customer_id: str | None) -> None:
    other = uow.customers.find_active_by_ico(ico)
    if other is not None and other.id != customer_id:
        raise Conflict(f"IČO {ico} is used by another active customer")


def add_customer(ctx: RequestContext, uow: TenancyUnitOfWork, cmd: CreateCustomer) -> CustomerView:
    """Creates the customer inside the caller's unit of work, which commits (a copy queues
    its job in the same transaction). Raises `ValidationFailed` for a bad identity or
    contact, `Conflict` for an IČO another active customer has."""
    if cmd.provider_id is None:
        ctx.require(Permission.CUSTOMERS_CREATE)
    else:
        ctx.require(Permission.CUSTOMERS_CREATE, provider_id=cmd.provider_id)
    errors = FieldErrors()
    parsed = _parse_identity(cmd.identity, errors)
    address, iban = _parse_contact(cmd.contact, errors)
    errors.raise_if_any("invalid customer")
    assert parsed is not None  # raise_if_any raised otherwise
    _require_unique_ico(uow, parsed.ico, None)
    customer = Customer.create(
        uow.ids.new(),
        parsed.name,
        parsed.ico,
        uow.clock.now(),
        dic=parsed.dic,
        address=address,
        iban=iban,
    )
    if cmd.provider_id is not None:
        customer.assign_to(uow.providers.get(cmd.provider_id))
    uow.customers.add(customer)
    _audit(ctx, uow, "customer.created", customer.id, {"provider_id": cmd.provider_id})
    return CustomerView.of(customer)


def create_customer(
    ctx: RequestContext, uow: TenancyUnitOfWork, cmd: CreateCustomer
) -> CustomerView:
    with uow:
        view = add_customer(ctx, uow, cmd)
        uow.commit()
    return view


def get_customer(ctx: RequestContext, uow: TenancyUnitOfWork, customer_id: str) -> CustomerView:
    ctx.require(Permission.CUSTOMER_READ, customer_id)
    with uow:
        return CustomerView.of(uow.customers.get(customer_id))


def update_identity(
    ctx: RequestContext, uow: TenancyUnitOfWork, customer_id: str, identity: CustomerIdentity
) -> CustomerView:
    ctx.require(Permission.CUSTOMER_EDIT_IDENTITY, customer_id)
    errors = FieldErrors()
    parsed = _parse_identity(identity, errors)
    errors.raise_if_any("invalid customer")
    assert parsed is not None  # raise_if_any raised otherwise
    with uow:
        customer = uow.customers.get(customer_id)
        if parsed.ico != customer.ico:
            _require_unique_ico(uow, parsed.ico, customer.id)
        before = (customer.name, customer.ico, customer.dic)
        customer.update_identity(parsed.name, parsed.ico, parsed.dic)
        uow.customers.save(customer)
        changed = [
            f
            for f, old, new in zip(
                ("name", "ico", "dic"),
                before,
                (customer.name, customer.ico, customer.dic),
                strict=True,
            )
            if old != new
        ]
        _audit(ctx, uow, "customer.identity_updated", customer.id, {"fields": changed})
        uow.commit()
    return CustomerView.of(customer)


def update_contact(
    ctx: RequestContext, uow: TenancyUnitOfWork, customer_id: str, contact: CustomerContact
) -> CustomerView:
    ctx.require(Permission.CUSTOMER_EDIT_CONTACT, customer_id)
    errors = FieldErrors()
    address, iban = _parse_contact(contact, errors)
    errors.raise_if_any("invalid customer")
    with uow:
        customer = uow.customers.get(customer_id)
        changed = [
            name
            for name, old, new in (
                ("address", customer.address, address),
                ("iban", customer.iban, iban),
            )
            if old != new
        ]
        customer.update_contact(address, iban)
        uow.customers.save(customer)
        _audit(ctx, uow, "customer.contact_updated", customer.id, {"fields": changed})
        uow.commit()
    return CustomerView.of(customer)


def assign_variable_number(
    ctx: RequestContext, uow: TenancyUnitOfWork, customer_id: str, variable_number: str | None
) -> CustomerView:
    ctx.require(Permission.CUSTOMER_ASSIGN_VARIABLE_NUMBER, customer_id)
    number = parse_variable_number(variable_number) if variable_number else None
    with uow:
        customer = uow.customers.get(customer_id)
        customer.assign_variable_number(number)
        uow.customers.save(customer)
        _audit(ctx, uow, "customer.variable_number_assigned", customer.id)
        uow.commit()
    return CustomerView.of(customer)


def delete_customer(ctx: RequestContext, uow: TenancyUnitOfWork, customer_id: str) -> CustomerView:
    ctx.require(Permission.CUSTOMERS_DELETE, customer_id)
    with uow:
        customer = uow.customers.get(customer_id)
        customer.delete(uow.clock.now())
        uow.customers.save(customer)
        _audit(ctx, uow, "customer.deleted", customer.id)
        uow.commit()
    return CustomerView.of(customer)


def restore_customer(ctx: RequestContext, uow: TenancyUnitOfWork, customer_id: str) -> CustomerView:
    ctx.require(Permission.CUSTOMERS_DELETE, customer_id)
    with uow:
        customer = uow.customers.get(customer_id)
        _require_unique_ico(uow, customer.ico, customer.id)
        customer.restore()
        uow.customers.save(customer)
        _audit(ctx, uow, "customer.restored", customer.id)
        uow.commit()
    return CustomerView.of(customer)


# Parameters -------------------------------------------------------------------------------


def get_parameters(
    ctx: RequestContext, uow: TenancyUnitOfWork, customer_id: str, year: int
) -> ParametersView:
    ctx.require(Permission.CUSTOMER_READ, customer_id)
    with uow:
        uow.customers.get(customer_id)
        parameters = uow.parameters.get(customer_id, year)
        if parameters is None:
            raise NotFound(f"no parameters of customer {customer_id} for {year}")
        return ParametersView.of(parameters)


def set_parameters(
    ctx: RequestContext,
    uow: TenancyUnitOfWork,
    customer_id: str,
    year: int,
    values: Mapping[str, Any],
) -> ParametersView:
    ctx.require(Permission.CODELISTS_EDIT, customer_id)
    parameters = CustomerParameters.parse(customer_id, year, values)
    with uow:
        uow.customers.get(customer_id)
        before = uow.parameters.get(customer_id, year)
        uow.parameters.save(parameters)
        _audit(
            ctx,
            uow,
            "customer.parameters_set",
            customer_id,
            {
                "year": year,
                "before": before.values() if before else None,
                "after": parameters.values(),
            },
        )
        uow.commit()
    return ParametersView.of(parameters)


def copy_parameters(
    ctx: RequestContext,
    uow: TenancyUnitOfWork,
    source_id: str,
    target_id: str,
    year: int,
    *,
    into_year: int | None = None,
) -> bool:
    """Gives the target the source's parameters of `year` for `into_year` (default the same
    year), inside the caller's unit of work (a customer copy, plan §9.3; a year's carry-over,
    §6.6). False when the source has none or the target already has some (a copy job run
    again changes nothing)."""
    ctx.require(Permission.CUSTOMER_READ, source_id)
    ctx.require(Permission.CODELISTS_EDIT, target_id)
    target_year = year if into_year is None else into_year
    source = uow.parameters.get(source_id, year)
    if source is None or uow.parameters.get(target_id, target_year) is not None:
        return False
    uow.parameters.save(CustomerParameters.parse(target_id, target_year, source.values()))
    return True


def purge_customer(
    ctx: RequestContext, uow: TenancyUnitOfWork, customer_id: str, typed_ico: str
) -> None:
    """Deletes a soft-deleted customer for good, with its parameters, its assignment and the
    memberships in it, after its IČO was typed to confirm (plan §5.6). The audit keeps its
    events. (Invoices arrive in P2-M4; the purge will warn about booked ones then.)"""
    ctx.require(Permission.CUSTOMERS_DELETE, customer_id)
    with uow:
        customer = uow.customers.get(customer_id)
        customer.confirm_purge(typed_ico)
        memberships = uow.logins.remove_customer_memberships(customer_id)
        uow.parameters.remove_all(customer_id)
        uow.customers.remove(customer_id)
        _audit(ctx, uow, "customer.purged", customer_id, {"memberships": memberships})
        uow.commit()
