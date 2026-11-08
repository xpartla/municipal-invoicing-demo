"""Service provider use cases (plan §5.6, §10.8–10.9): creating and removing providers,
assigning customers, and the overview and user lists.

Removing a provider keeps its row, deactivates its staff memberships and leaves its customers
unassigned (plan §2 decision 38), in one transaction.
"""

from dataclasses import dataclass

from riso.identity import Permission
from riso.shared.context import RequestContext
from riso.shared.errors import FieldErrors
from riso.shared.values import Ico, clean_name
from riso.tenancy.application.customers import TenancyUnitOfWork, _audit
from riso.tenancy.application.ports import LoginRef
from riso.tenancy.application.views import CustomerView, ProviderView
from riso.tenancy.domain import ServiceProvider


@dataclass(frozen=True, slots=True)
class ProviderOverview:
    provider: ProviderView
    customers: tuple[CustomerView, ...]
    """The active customers assigned to it, by name."""


@dataclass(frozen=True, slots=True)
class ProviderDetail:
    provider: ProviderView
    staff: tuple[LoginRef, ...]
    customers: tuple[CustomerView, ...]


@dataclass(frozen=True, slots=True)
class CustomerWithLogins:
    customer: CustomerView
    logins: tuple[LoginRef, ...]


def get_provider(ctx: RequestContext, uow: TenancyUnitOfWork, provider_id: str) -> ProviderOverview:
    ctx.require(Permission.PROVIDER_OVERVIEW, provider_id=provider_id)
    with uow:
        provider = uow.providers.get(provider_id)
        customers = uow.customers.find(provider_id=provider_id)
        return ProviderOverview(
            ProviderView.of(provider), tuple(CustomerView.of(c) for c in customers)
        )


def create_provider(
    ctx: RequestContext, uow: TenancyUnitOfWork, name: str, ico: str | None = None
) -> ProviderView:
    ctx.require(Permission.PROVIDERS_MANAGE)
    errors = FieldErrors()
    cleaned = errors.check(lambda: clean_name(name))
    parsed = errors.check(lambda: Ico.parse(ico)) if ico else None
    errors.raise_if_any("invalid provider")
    assert cleaned is not None
    with uow:
        provider = ServiceProvider.create(uow.ids.new(), cleaned, uow.clock.now(), ico=parsed)
        uow.providers.add(provider)
        uow.audit.record(ctx, "provider.created", target_type="provider", target_id=provider.id)
        uow.commit()
    return ProviderView.of(provider)


def remove_provider(ctx: RequestContext, uow: TenancyUnitOfWork, provider_id: str) -> ProviderView:
    ctx.require(Permission.PROVIDERS_MANAGE)
    with uow:
        provider = uow.providers.get(provider_id)
        provider.remove(uow.clock.now())
        uow.providers.save(provider)
        customers = uow.customers.assigned_to(provider_id)
        for customer in customers:
            customer.unassign()
            uow.customers.save(customer)
            _audit(
                ctx, uow, "customer.provider_unassigned", customer.id, {"provider_id": provider_id}
            )
        staff = uow.logins.deactivate_staff(provider_id)
        uow.audit.record(
            ctx,
            "provider.removed",
            target_type="provider",
            target_id=provider.id,
            details={"customers": len(customers), "staff": staff},
        )
        uow.commit()
    return ProviderView.of(provider)


def assign_provider(
    ctx: RequestContext, uow: TenancyUnitOfWork, customer_id: str, provider_id: str
) -> CustomerView:
    ctx.require(Permission.PROVIDERS_MANAGE)
    with uow:
        customer = uow.customers.get(customer_id)
        customer.assign_to(uow.providers.get(provider_id))
        uow.customers.save(customer)
        _audit(ctx, uow, "customer.provider_assigned", customer.id, {"provider_id": provider_id})
        uow.commit()
    return CustomerView.of(customer)


def unassign_provider(
    ctx: RequestContext, uow: TenancyUnitOfWork, customer_id: str
) -> CustomerView:
    ctx.require(Permission.PROVIDERS_MANAGE)
    with uow:
        customer = uow.customers.get(customer_id)
        previous = customer.provider_id
        customer.unassign()
        uow.customers.save(customer)
        _audit(ctx, uow, "customer.provider_unassigned", customer.id, {"provider_id": previous})
        uow.commit()
    return CustomerView.of(customer)


def list_providers(
    ctx: RequestContext, uow: TenancyUnitOfWork, *, include_removed: bool = False
) -> list[ProviderDetail]:
    """Every provider with its active staff and its active customers (Servisné účty)."""
    ctx.require(Permission.PROVIDERS_MANAGE)
    with uow:
        providers = uow.providers.find(include_removed=include_removed)
        staff = uow.logins.staff_of([p.id for p in providers])
        return [
            ProviderDetail(
                ProviderView.of(p),
                tuple(staff.get(p.id, [])),
                tuple(CustomerView.of(c) for c in uow.customers.find(provider_id=p.id)),
            )
            for p in providers
        ]


def customer_directory(
    ctx: RequestContext,
    uow: TenancyUnitOfWork,
    *,
    provider_id: str | None = None,
    include_deleted: bool = False,
) -> list[CustomerWithLogins]:
    """The customers with their logins nested (Používatelia): a provider's for its staff
    (and admins), or every customer for admins when `provider_id` is None."""
    if provider_id is None:
        ctx.require(Permission.PROVIDER_OVERVIEW)
    else:
        ctx.require(Permission.PROVIDER_OVERVIEW, provider_id=provider_id)
    with uow:
        customers = uow.customers.find(provider_id=provider_id, include_deleted=include_deleted)
        logins = uow.logins.of_customers([c.id for c in customers])
        return [
            CustomerWithLogins(CustomerView.of(c), tuple(logins.get(c.id, []))) for c in customers
        ]
