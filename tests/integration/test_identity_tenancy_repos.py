"""The identity and tenancy repositories: round trips on a migrated SQLite file, with the
in-memory fakes run through the same tests so they cannot drift from the real ones."""

import inspect
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from riso.identity.domain import Email, MembershipScope, Role, ScopeKind, User, UserRepository
from riso.identity.infrastructure.repository import SqlUserRepository
from riso.identity.infrastructure.uow import SqlIdentityUnitOfWork
from riso.shared import Conflict, FixedClock, Iban, Ico, NotFound, UuidV7Generator
from riso.tenancy.domain import (
    Address,
    Customer,
    CustomerParameters,
    CustomerStatus,
    ParametersRepository,
    ServiceProvider,
)
from riso.tenancy.infrastructure.repository import SqlParametersRepository
from riso.tenancy.infrastructure.uow import SqlTenancyUnitOfWork
from tests.fakes.identity import InMemoryIdentityUnitOfWork
from tests.fakes.tenancy import InMemoryTenancyUnitOfWork
from tests.unit.tenancy.test_parameters import VALUES

T0 = datetime(2026, 6, 11, 8, 0, tzinfo=UTC)


@pytest.fixture
def clock():
    return FixedClock(T0)


@pytest.fixture(params=["sql", "memory"])
def identity(request, migrated, clock):
    if request.param == "sql":
        return lambda: SqlIdentityUnitOfWork(migrated, clock=clock, ids=UuidV7Generator(clock))
    fake = InMemoryIdentityUnitOfWork(clock=clock)
    return lambda: fake


@pytest.fixture(params=["sql", "memory"])
def tenancy(request, migrated, clock):
    if request.param == "sql":
        return lambda: SqlTenancyUnitOfWork(migrated, clock=clock, ids=UuidV7Generator(clock))
    fake = InMemoryTenancyUnitOfWork(clock=clock)
    return lambda: fake


def jana(user_id="u1", email="jana@obec.sk", name="Jana Vzorová") -> User:
    user = User.invite(user_id, name, Email(email), T0)
    user.set_password("$argon2id$hash", T0)
    return user


# Users ------------------------------------------------------------------------------------


def test_a_user_round_trips_with_its_memberships(identity):
    user = jana()
    user.set_notification_email(Email("notify@obec.sk"))
    user.lock(T0 + timedelta(minutes=5))
    user.grant("m1", MembershipScope.customer("c1"), Role.CUSTOMER_USER, T0)
    user.grant("m2", MembershipScope.provider("p1"), Role.PROVIDER_STAFF, T0)
    user.grant("m3", MembershipScope.platform(), Role.PLATFORM_ADMIN, T0)
    user.deactivate_membership(MembershipScope.provider("p1"), T0 + timedelta(hours=1))
    with identity() as uow:
        uow.users.add(user)
        uow.commit()
    with identity() as uow:
        loaded = uow.users.get("u1")
    assert loaded == user
    assert [m.id for m in loaded.memberships] == ["m1", "m2", "m3"]


def test_saving_adds_updates_and_removes_memberships(identity):
    with identity() as uow:
        user = jana()
        user.grant("m1", MembershipScope.customer("c1"), Role.CUSTOMER_USER, T0)
        uow.users.add(user)
        uow.commit()
    with identity() as uow:
        user = uow.users.get("u1")
        user.grant("m2", MembershipScope.customer("c2"), Role.CUSTOMER_VIEWER, T0)
        user.deactivate_membership(MembershipScope.customer("c1"), T0)
        user.rename("Jana Nová")
        uow.users.save(user)
        uow.commit()
    with identity() as uow:
        user = uow.users.get("u1")
        assert user.name == "Jana Nová"
        assert [(m.id, m.active) for m in user.memberships] == [("m1", False), ("m2", True)]
        user.delete(T0)
        user.purge(T0)
        uow.users.save(user)
        uow.commit()
    with identity() as uow:
        purged = uow.users.get("u1")
    assert (purged.email, purged.memberships, purged.name) == (None, [], "")


def test_finding_users(identity):
    with identity() as uow:
        a = jana("u1", "jana@obec.sk", "Jana Vzorová")
        a.grant("m1", MembershipScope.customer("c1"), Role.CUSTOMER_USER, T0)
        b = jana("u2", "ivan@obec.sk", "Ivan Čitateľ")
        b.grant("m2", MembershipScope.customer("c1"), Role.CUSTOMER_VIEWER, T0)
        b.grant("m3", MembershipScope.customer("c2"), Role.CUSTOMER_VIEWER, T0)
        c = jana("u3", "peter@vzor.sk", "Peter Účtovník")
        c.grant("m4", MembershipScope.provider("p1"), Role.PROVIDER_STAFF, T0)
        d = jana("u4", "gone@obec.sk", "Zuzana Preč")
        d.delete(T0)
        for user in (a, b, c, d):
            uow.users.add(user)
        uow.commit()
    with identity() as uow:
        assert uow.users.find_by_email(Email("ivan@obec.sk")).id == "u2"
        assert uow.users.find_by_email(Email("nobody@obec.sk")) is None
        assert [u.id for u in uow.users.members_of_customer("c1")] == ["u2", "u1"]
        assert [u.id for u in uow.users.with_memberships_in(ScopeKind.CUSTOMER, ["c2"])] == ["u2"]
        assert [u.id for u in uow.users.with_memberships_in(ScopeKind.PROVIDER, ["p1"])] == ["u3"]
        assert uow.users.with_memberships_in(ScopeKind.CUSTOMER, []) == []
        assert [u.id for u in uow.users.find()] == ["u2", "u1", "u3"]
        assert [u.id for u in uow.users.find(include_deleted=True)] == ["u2", "u1", "u3", "u4"]
        assert [u.id for u in uow.users.find(query="VZOR")] == ["u1", "u3"]
        assert [u.id for u in uow.users.find(query="100%")] == []
        with pytest.raises(NotFound):
            uow.users.get("nobody")


def test_the_login_email_is_unique(identity, request):
    with identity() as uow:
        uow.users.add(jana("u1"))
        uow.commit()
    with pytest.raises((IntegrityError, Conflict)), identity() as uow:
        uow.users.add(jana("u2"))
        uow.commit()


# Customers, providers, parameters ---------------------------------------------------------


def boldog(customer_id="c1", ico="00305863") -> Customer:
    return Customer.create(
        customer_id,
        "Obec Boldog",
        Ico(ico),
        T0,
        dic="2021009530",
        address=Address.parse("Boldog 12", "Boldog", "92528"),
        iban=Iban.parse("SK3112000000198742637541"),
    )


def test_a_customer_round_trips_with_its_provider(tenancy):
    with tenancy() as uow:
        provider = ServiceProvider.create("p1", "Účtovníctvo Vzor, s.r.o.", T0, ico=Ico("00305871"))
        uow.providers.add(provider)
        customer = boldog()
        customer.assign_variable_number("305863")
        customer.assign_to(provider)
        uow.customers.add(customer)
        uow.customers.add(Customer.create("c2", "Obec Bez Adresy", Ico("00305871"), T0))
        uow.commit()
    with tenancy() as uow:
        assert uow.customers.get("c1") == customer
        assert uow.customers.get("c2").address is None
        assert uow.providers.get("p1") == provider


def test_assignment_changes_are_saved(tenancy):
    with tenancy() as uow:
        p1 = ServiceProvider.create("p1", "Prvá", T0)
        p2 = ServiceProvider.create("p2", "Druhá", T0)
        uow.providers.add(p1)
        uow.providers.add(p2)
        customer = boldog()
        customer.assign_to(p1)
        uow.customers.add(customer)
        uow.commit()
    with tenancy() as uow:
        customer = uow.customers.get("c1")
        customer.unassign()
        customer.assign_to(uow.providers.get("p2"))
        uow.customers.save(customer)
        uow.commit()
    with tenancy() as uow:
        assert uow.customers.get("c1").provider_id == "p2"
        assert [c.id for c in uow.customers.find(provider_id="p2")] == ["c1"]
        assert uow.customers.find(provider_id="p1") == []
        customer = uow.customers.get("c1")
        customer.unassign()
        uow.customers.save(customer)
        uow.commit()
    with tenancy() as uow:
        assert uow.customers.get("c1").provider_id is None


def test_finding_customers(tenancy):
    with tenancy() as uow:
        uow.providers.add(ServiceProvider.create("p1", "Vzor", T0))
        a = boldog("c1", "00305863")
        a.assign_to(uow.providers.get("p1"))
        b = Customer.create("c2", "Obec Agátová", Ico("00305871"), T0)
        c = Customer.create("c3", "Obec Zrušená", Ico("00305880"), T0)
        c.assign_to(uow.providers.get("p1"))
        c.delete(T0)
        for customer in (a, b, c):
            uow.customers.add(customer)
        uow.commit()
    with tenancy() as uow:
        assert [x.id for x in uow.customers.find()] == ["c2", "c1"]
        assert [x.id for x in uow.customers.find(include_deleted=True)] == ["c2", "c1", "c3"]
        assert [x.id for x in uow.customers.find(provider_id="p1")] == ["c1"]
        assert sorted(x.id for x in uow.customers.assigned_to("p1")) == ["c1", "c3"]
        assert uow.customers.find_active_by_ico(Ico("00305863")).id == "c1"
        assert uow.customers.find_active_by_ico(Ico("00305880")) is None  # deleted


def test_removing_a_customer_and_its_rows(tenancy):
    with tenancy() as uow:
        uow.providers.add(ServiceProvider.create("p1", "Vzor", T0))
        customer = boldog()
        customer.assign_to(uow.providers.get("p1"))
        uow.customers.add(customer)
        uow.parameters.save(CustomerParameters.parse("c1", 2026, VALUES))
        uow.commit()
    with tenancy() as uow:
        uow.parameters.remove_all("c1")
        uow.customers.remove("c1")
        uow.commit()
    with tenancy() as uow:
        with pytest.raises(NotFound):
            uow.customers.get("c1")
        assert uow.parameters.years("c1") == []
        assert uow.customers.assigned_to("p1") == []


def test_parameters_round_trip_per_year(tenancy):
    with tenancy() as uow:
        uow.customers.add(boldog())
        uow.parameters.save(CustomerParameters.parse("c1", 2026, VALUES))
        uow.parameters.save(CustomerParameters.parse("c1", 2027, {**VALUES, "vat_payer": True}))
        uow.commit()
    with tenancy() as uow:
        assert uow.parameters.get("c1", 2026).values() == VALUES
        assert uow.parameters.get("c1", 2027).vat_payer is True
        assert uow.parameters.get("c1", 2028) is None
        assert uow.parameters.years("c1") == [2026, 2027]
        uow.parameters.save(CustomerParameters.parse("c1", 2026, {**VALUES, "default_zdroj": "46"}))
        uow.commit()
    with tenancy() as uow:
        assert uow.parameters.get("c1", 2026).default_zdroj == "46"


def test_a_provider_removal_round_trips(tenancy):
    with tenancy() as uow:
        uow.providers.add(ServiceProvider.create("p1", "Vzor", T0))
        uow.providers.add(ServiceProvider.create("p2", "Agát", T0))
        uow.commit()
    with tenancy() as uow:
        provider = uow.providers.get("p1")
        provider.remove(T0)
        uow.providers.save(provider)
        uow.commit()
    with tenancy() as uow:
        assert [p.id for p in uow.providers.find()] == ["p2"]
        assert [p.id for p in uow.providers.find(include_removed=True)] == ["p2", "p1"]
        assert uow.providers.get("p1").status.value == "removed"


def test_uncommitted_work_is_rolled_back(tenancy):
    with tenancy() as uow:
        uow.customers.add(boldog())
        uow.commit()
    with tenancy() as uow:
        customer = uow.customers.get("c1")
        customer.delete(T0)
        uow.customers.save(customer)
    with tenancy() as uow:
        assert uow.customers.get("c1").status is CustomerStatus.ACTIVE


def test_customer_scoped_repository_methods_take_the_customer_id():
    """Guide §6.4: no method reads a customer's data without its ID."""
    scoped = {
        (ParametersRepository, SqlParametersRepository): ["get", "years", "remove_all"],
        (UserRepository, SqlUserRepository): ["members_of_customer"],
    }
    for classes, names in scoped.items():
        for cls in classes:
            for name in names:
                params = list(inspect.signature(getattr(cls, name)).parameters)
                assert params[1] == "customer_id", (cls.__name__, name, params)
    # The parameters' own key carries it too.
    assert "customer_id" in inspect.signature(CustomerParameters).parameters
