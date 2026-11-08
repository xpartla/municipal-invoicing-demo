"""Service provider use cases (plan §5.6, §10.8–10.9)."""

from dataclasses import dataclass

from riso.identity import Permission
from riso.shared.context import RequestContext
from riso.tenancy.application.customers import TenancyUnitOfWork
from riso.tenancy.application.views import CustomerView, ProviderView


@dataclass(frozen=True, slots=True)
class ProviderOverview:
    provider: ProviderView
    customers: tuple[CustomerView, ...]
    """The active customers assigned to it, by name."""


def get_provider(ctx: RequestContext, uow: TenancyUnitOfWork, provider_id: str) -> ProviderOverview:
    ctx.require(Permission.PROVIDER_OVERVIEW, provider_id=provider_id)
    with uow:
        provider = uow.providers.get(provider_id)
        customers = uow.customers.find(provider_id=provider_id)
        return ProviderOverview(
            ProviderView.of(provider), tuple(CustomerView.of(c) for c in customers)
        )
