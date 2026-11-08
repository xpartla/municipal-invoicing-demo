"""Shared factories (guide §6.9): customers, providers and users per role, written straight
through the application's unit of work. Made-up people and organisations only."""

from riso.api.composition import Services
from riso.identity.domain import Email, MembershipScope, Role, User
from riso.shared import Ico
from riso.tenancy.domain import Customer, ServiceProvider

PASSWORD = "Správne-heslo-2026"


def make_provider(services: Services, name: str = "Účtovníctvo Vzor, s.r.o.") -> str:
    with services.uow() as uow:
        provider = ServiceProvider.create(uow.ids.new(), name, uow.clock.now())
        uow.providers.add(provider)
        uow.commit()
    return provider.id


def make_customer(
    services: Services,
    name: str = "Obec Boldog",
    ico: str = "00305863",
    provider_id: str | None = None,
) -> str:
    with services.uow() as uow:
        customer = Customer.create(uow.ids.new(), name, Ico(ico), uow.clock.now())
        if provider_id is not None:
            customer.assign_to(uow.providers.get(provider_id))
        uow.customers.add(customer)
        uow.commit()
    return customer.id


def make_user(
    services: Services,
    email: str,
    *,
    name: str = "Jana Vzorová",
    password: str | None = PASSWORD,
    role: Role | None = None,
    scope_id: str | None = None,
) -> str:
    """A user, active with `password` (invited without one), holding `role` in `scope_id`
    (the platform for the admin role)."""
    with services.uow() as uow:
        now = uow.clock.now()
        user = User.invite(uow.ids.new(), name, Email.parse(email), now)
        if password is not None:
            user.set_password(services.hasher.hash(password), now)
        if role is not None:
            scope = {
                Role.CUSTOMER_VIEWER: MembershipScope.customer,
                Role.CUSTOMER_USER: MembershipScope.customer,
                Role.PROVIDER_STAFF: MembershipScope.provider,
            }.get(role)
            target = scope(scope_id) if scope and scope_id else MembershipScope.platform()
            user.grant(uow.ids.new(), target, role, now)
        uow.users.add(user)
        uow.commit()
    return user.id


def update_user(services: Services, user_id: str, change) -> None:
    with services.uow() as uow:
        user = uow.users.get(user_id)
        change(user, uow.clock.now())
        uow.users.save(user)
        uow.commit()
