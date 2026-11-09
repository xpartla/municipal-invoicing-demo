"""The tenancy API: customers (`/api/customers/{customer_id}`) and providers
(`/api/providers/{provider_id}`)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from riso.api.deps import (
    Caller,
    ServicesDep,
    check_csrf,
    customer_context,
    platform_context,
    provider_context,
)
from riso.exchange import CopyCustomer, CopyOptions, copy_customer
from riso.identity import Permission
from riso.shared.errors import ValidationFailed
from riso.tenancy.api.models import (
    AddressIn,
    AdminCustomerCopyIn,
    AdminCustomerIn,
    AssignProviderIn,
    CustomerContactIn,
    CustomerCopyIn,
    CustomerCopyOut,
    CustomerIdentityIn,
    CustomerIn,
    CustomerOut,
    CustomerWithLoginsOut,
    ParametersIn,
    ParametersOut,
    ProviderDetailOut,
    ProviderIn,
    ProviderOut,
    ProviderOverviewOut,
    PurgeIn,
    VariableNumberIn,
)
from riso.tenancy.application import (
    AddressInput,
    CreateCustomer,
    CustomerContact,
    CustomerIdentity,
    assign_provider,
    assign_variable_number,
    create_customer,
    create_provider,
    customer_directory,
    delete_customer,
    get_customer,
    get_parameters,
    get_provider,
    list_providers,
    purge_customer,
    remove_provider,
    restore_customer,
    set_parameters,
    unassign_provider,
    update_contact,
    update_identity,
)

router = APIRouter(prefix="/api", dependencies=[Depends(check_csrf)], tags=["tenancy"])


@router.get("/customers/{customer_id}", name="customers.get")
def customer_get(
    caller: Annotated[Caller, Depends(customer_context(Permission.CUSTOMER_READ))],
    services: ServicesDep,
    customer_id: str,
) -> CustomerOut:
    """The customer's profile."""
    return CustomerOut.of(get_customer(caller.ctx, services.uow(immediate=False), customer_id))


@router.patch("/customers/{customer_id}/contact", name="customers.update_contact")
def customer_update_contact(
    caller: Annotated[Caller, Depends(customer_context(Permission.CUSTOMER_EDIT_CONTACT))],
    services: ServicesDep,
    customer_id: str,
    body: CustomerContactIn,
) -> CustomerOut:
    """The customer's address and bank account (users, staff and admins)."""
    return CustomerOut.of(update_contact(caller.ctx, services.uow(), customer_id, _contact(body)))


@router.get("/providers/{provider_id}", name="providers.get")
def provider_get(
    caller: Annotated[Caller, Depends(provider_context(Permission.PROVIDER_OVERVIEW))],
    services: ServicesDep,
    provider_id: str,
) -> ProviderOverviewOut:
    """The provider and its active customers."""
    return ProviderOverviewOut.of(
        get_provider(caller.ctx, services.uow(immediate=False), provider_id)
    )


def _address(a: AddressIn | None) -> AddressInput | None:
    return AddressInput(a.street, a.city, a.postal_code, a.country) if a else None


def _contact(body: CustomerContactIn) -> CustomerContact:
    return CustomerContact(address=_address(body.address), iban=body.iban)


def _create(body: CustomerIn, provider_id: str | None) -> CreateCustomer:
    return CreateCustomer(
        CustomerIdentity(body.name, body.ico, body.dic), _contact(body), provider_id=provider_id
    )


CustomerDeleter = Annotated[Caller, Depends(customer_context(Permission.CUSTOMERS_DELETE))]
ProviderManager = Annotated[Caller, Depends(platform_context(Permission.PROVIDERS_MANAGE))]


@router.patch("/customers/{customer_id}/identity", name="customers.update_identity")
def customer_update_identity(
    caller: Annotated[Caller, Depends(customer_context(Permission.CUSTOMER_EDIT_IDENTITY))],
    services: ServicesDep,
    customer_id: str,
    body: CustomerIdentityIn,
) -> CustomerOut:
    """Name, IČO and DIČ (staff and admins, plan §2 decision 50). The IČO stays unique among
    active customers (409)."""
    identity = CustomerIdentity(body.name, body.ico, body.dic)
    return CustomerOut.of(update_identity(caller.ctx, services.uow(), customer_id, identity))


@router.put("/customers/{customer_id}/variable-number", name="customers.assign_variable_number")
def customer_variable_number(
    caller: Annotated[
        Caller, Depends(customer_context(Permission.CUSTOMER_ASSIGN_VARIABLE_NUMBER))
    ],
    services: ServicesDep,
    customer_id: str,
    body: VariableNumberIn,
) -> CustomerOut:
    """The customer's variable number (staff and admins); null clears it."""
    return CustomerOut.of(
        assign_variable_number(caller.ctx, services.uow(), customer_id, body.variable_number)
    )


@router.delete("/customers/{customer_id}", name="customers.delete")
def customer_delete(
    caller: CustomerDeleter, services: ServicesDep, customer_id: str
) -> CustomerOut:
    """Soft delete (admins): hidden from everyone else, restorable."""
    return CustomerOut.of(delete_customer(caller.ctx, services.uow(), customer_id))


@router.post("/customers/{customer_id}/restore", name="customers.restore")
def customer_restore(
    caller: CustomerDeleter, services: ServicesDep, customer_id: str
) -> CustomerOut:
    return CustomerOut.of(restore_customer(caller.ctx, services.uow(), customer_id))


@router.post("/customers/{customer_id}/purge", name="customers.purge", status_code=204)
def customer_purge(
    caller: CustomerDeleter, services: ServicesDep, customer_id: str, body: PurgeIn
) -> None:
    """Deletes a soft-deleted customer for good; its IČO must be typed to confirm."""
    purge_customer(caller.ctx, services.uow(), customer_id, body.ico_confirmation)


# Creating customers and the user lists ---------------------------------------------------


@router.post(
    "/providers/{provider_id}/customers", name="providers.create_customer", status_code=201
)
def provider_create_customer(
    caller: Annotated[Caller, Depends(provider_context(Permission.CUSTOMERS_CREATE))],
    services: ServicesDep,
    provider_id: str,
    body: CustomerIn,
) -> CustomerOut:
    """A new customer in the staff member's own provider."""
    return CustomerOut.of(create_customer(caller.ctx, services.uow(), _create(body, provider_id)))


def _copy(
    caller: Caller, services: ServicesDep, body: CustomerCopyIn, provider_id: str | None
) -> CustomerCopyOut:
    started = copy_customer(
        caller.ctx,
        services.uow(),
        CopyCustomer(
            body.source_customer_id,
            _create(body, provider_id),
            CopyOptions.model_validate(body.options.model_dump()),
        ),
    )
    return CustomerCopyOut(customer=CustomerOut.of(started.customer), job_id=started.job_id)


@router.post(
    "/providers/{provider_id}/customers/copy",
    name="providers.copy_customer",
    status_code=202,
)
def provider_copy_customer(
    caller: Annotated[Caller, Depends(provider_context(Permission.CUSTOMERS_CREATE))],
    services: ServicesDep,
    provider_id: str,
    body: CustomerCopyIn,
) -> CustomerCopyOut:
    """A new customer in the staff member's provider as a copy of one of its customers. The
    copy runs as a job; follow it at `/api/customers/{id}/jobs/{job_id}`."""
    return _copy(caller, services, body, provider_id)


@router.get("/providers/{provider_id}/customers", name="providers.directory")
def provider_directory(
    caller: Annotated[Caller, Depends(provider_context(Permission.PROVIDER_OVERVIEW))],
    services: ServicesDep,
    provider_id: str,
) -> list[CustomerWithLoginsOut]:
    """The provider's customers with their logins nested (Používatelia)."""
    found = customer_directory(caller.ctx, services.uow(immediate=False), provider_id=provider_id)
    return [CustomerWithLoginsOut.of(c) for c in found]


@router.post("/admin/customers", name="customers.create", status_code=201)
def admin_create_customer(
    caller: Annotated[Caller, Depends(platform_context(Permission.CUSTOMERS_CREATE))],
    services: ServicesDep,
    body: AdminCustomerIn,
) -> CustomerOut:
    """A new customer, in a provider or unassigned (admins)."""
    return CustomerOut.of(
        create_customer(caller.ctx, services.uow(), _create(body, body.provider_id))
    )


@router.post("/admin/customers/copy", name="customers.copy", status_code=202)
def admin_copy_customer(
    caller: Annotated[Caller, Depends(platform_context(Permission.CUSTOMERS_CREATE))],
    services: ServicesDep,
    body: AdminCustomerCopyIn,
) -> CustomerCopyOut:
    """A new customer as a copy of any customer, in a provider or unassigned (admins)."""
    return _copy(caller, services, body, body.provider_id)


@router.get("/admin/customers", name="customers.directory")
def admin_directory(
    caller: Annotated[Caller, Depends(platform_context(Permission.PROVIDER_OVERVIEW))],
    services: ServicesDep,
    include_deleted: bool = False,
) -> list[CustomerWithLoginsOut]:
    """Every customer with its logins nested (admins)."""
    found = customer_directory(
        caller.ctx, services.uow(immediate=False), include_deleted=include_deleted
    )
    return [CustomerWithLoginsOut.of(c) for c in found]


# Providers (admins) -------------------------------------------------------------------------


@router.get("/admin/providers", name="providers.list")
def providers_list(
    caller: ProviderManager, services: ServicesDep, include_removed: bool = False
) -> list[ProviderDetailOut]:
    """Every provider with its staff and customers (Servisné účty)."""
    found = list_providers(
        caller.ctx, services.uow(immediate=False), include_removed=include_removed
    )
    return [ProviderDetailOut.of(p) for p in found]


@router.post("/admin/providers", name="providers.create", status_code=201)
def providers_create(
    caller: ProviderManager, services: ServicesDep, body: ProviderIn
) -> ProviderOut:
    return ProviderOut.of(create_provider(caller.ctx, services.uow(), body.name, body.ico))


@router.delete("/admin/providers/{provider_id}", name="providers.remove")
def providers_remove(
    caller: ProviderManager, services: ServicesDep, provider_id: str
) -> ProviderOut:
    """Removes the provider: its customers become unassigned and its staff memberships are
    deactivated."""
    return ProviderOut.of(remove_provider(caller.ctx, services.uow(), provider_id))


@router.put("/admin/customers/{customer_id}/provider", name="customers.assign_provider")
def customers_assign(
    caller: ProviderManager, services: ServicesDep, customer_id: str, body: AssignProviderIn
) -> CustomerOut:
    """Assigns the customer to a provider; one already assigned elsewhere is a 409."""
    return CustomerOut.of(
        assign_provider(caller.ctx, services.uow(), customer_id, body.provider_id)
    )


@router.delete("/admin/customers/{customer_id}/provider", name="customers.unassign_provider")
def customers_unassign(
    caller: ProviderManager, services: ServicesDep, customer_id: str
) -> CustomerOut:
    return CustomerOut.of(unassign_provider(caller.ctx, services.uow(), customer_id))


ParametersYear = Annotated[int, Query(ge=2000, le=2100)]


@router.get("/customers/{customer_id}/parameters", name="parameters.get")
def parameters_get(
    caller: Annotated[Caller, Depends(customer_context(Permission.CUSTOMER_READ))],
    services: ServicesDep,
    customer_id: str,
    year: ParametersYear,
) -> ParametersOut:
    """The customer's parameters for the year (plan §6.4); 404 while it has none."""
    found = get_parameters(caller.ctx, services.uow(immediate=False), customer_id, year)
    return ParametersOut.of(found)


@router.put("/customers/{customer_id}/parameters", name="parameters.set")
def parameters_set(
    caller: Annotated[Caller, Depends(customer_context(Permission.CODELISTS_EDIT))],
    services: ServicesDep,
    customer_id: str,
    year: ParametersYear,
    body: ParametersIn,
) -> ParametersOut:
    """Sets the customer's parameters for the year; 422 names each invalid field."""
    try:
        found = set_parameters(caller.ctx, services.uow(), customer_id, year, body.values)
    except ValidationFailed as exc:
        raise exc.under("values") from exc
    return ParametersOut.of(found)
