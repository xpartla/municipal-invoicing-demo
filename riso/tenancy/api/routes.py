"""The tenancy API: customers (`/api/customers/{customer_id}`) and providers
(`/api/providers/{provider_id}`)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from riso.api.deps import Caller, ServicesDep, check_csrf, customer_context, provider_context
from riso.identity import Permission
from riso.tenancy.api.models import CustomerOut, ProviderOverviewOut
from riso.tenancy.application import get_customer, get_provider

router = APIRouter(prefix="/api", dependencies=[Depends(check_csrf)], tags=["tenancy"])


@router.get("/customers/{customer_id}", name="customers.get")
def customer_get(
    caller: Annotated[Caller, Depends(customer_context(Permission.CUSTOMER_READ))],
    services: ServicesDep,
    customer_id: str,
) -> CustomerOut:
    """The customer's profile."""
    return CustomerOut.of(get_customer(caller.ctx, services.uow(immediate=False), customer_id))


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
