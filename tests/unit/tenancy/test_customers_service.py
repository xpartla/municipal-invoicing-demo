"""The customer use cases with in-memory repositories: IČO uniqueness among active customers,
the permission checked first, and the field errors gathered."""

import pytest

from riso.identity import Permission
from riso.shared import (
    Conflict,
    NotFound,
    PermissionDenied,
    RequestContext,
    ValidationFailed,
)
from riso.tenancy.application import (
    AddressInput,
    CreateCustomer,
    CustomerContact,
    CustomerIdentity,
    create_customer,
    delete_customer,
    get_customer,
    get_parameters,
    restore_customer,
    set_parameters,
    update_contact,
    update_identity,
)
from riso.tenancy.domain import CustomerParameters, CustomerStatus, ServiceProvider
from tests.fakes.access import Grants
from tests.fakes.tenancy import InMemoryTenancyUnitOfWork
from tests.unit.tenancy.test_parameters import VALUES

SYSTEM = RequestContext.system("r1")


@pytest.fixture
def uow():
    return InMemoryTenancyUnitOfWork()


def new(uow, ico="00305863", name="Obec Boldog", **kwargs):
    return create_customer(
        SYSTEM, uow, CreateCustomer(CustomerIdentity(name=name, ico=ico), **kwargs)
    )


def test_creating_a_customer(uow):
    view = new(uow, contact=CustomerContact(AddressInput("Boldog 12", "Boldog", "925 28")))
    assert (view.name, view.ico, view.status, view.address.postal_code) == (
        "Obec Boldog",
        "00305863",
        CustomerStatus.ACTIVE,
        "92528",
    )
    assert get_customer(SYSTEM, uow, view.id) == view
    assert uow.commits == 1


def test_the_ico_is_unique_among_active_customers(uow):
    first = new(uow)
    with pytest.raises(Conflict, match="00305863"):
        new(uow, name="Obec Boldog 2")
    with pytest.raises(Conflict):
        new(uow, ico="305863")  # the same IČO, typed without its leading zeros
    assert len(uow.customers.rows) == 1

    delete_customer(SYSTEM, uow, first.id)
    second = new(uow, name="Obec Boldog 2")  # a deleted customer's IČO is free again
    with pytest.raises(Conflict):
        restore_customer(SYSTEM, uow, first.id)
    assert uow.customers.get(first.id).status is CustomerStatus.DELETED

    delete_customer(SYSTEM, uow, second.id)
    assert restore_customer(SYSTEM, uow, first.id).status is CustomerStatus.ACTIVE


def test_changing_the_ico_checks_it_too(uow):
    boldog = new(uow)
    other = new(uow, ico="00305871", name="Obec Vzorová")
    with pytest.raises(Conflict):
        update_identity(SYSTEM, uow, other.id, CustomerIdentity("Obec Vzorová", "00305863"))
    renamed = update_identity(SYSTEM, uow, boldog.id, CustomerIdentity("Boldog", "00305863"))
    assert renamed.name == "Boldog"


def test_field_errors_are_gathered(uow):
    with pytest.raises(ValidationFailed) as caught:
        create_customer(
            SYSTEM,
            uow,
            CreateCustomer(
                CustomerIdentity(name=" ", ico="00305864", dic="123"),
                CustomerContact(AddressInput("x", "y", "1"), iban="SK00 1234"),
            ),
        )
    assert sorted(e.field for e in caught.value.errors) == [
        "address.postal_code",
        "dic",
        "iban",
        "ico",
        "name",
    ]
    assert uow.customers.rows == {}


def test_creating_into_a_provider_assigns_the_customer(uow):
    uow.providers.add(ServiceProvider.create("p1", "Účtovníctvo Vzor, s.r.o.", uow.clock.now()))
    view = new(uow, provider_id="p1")
    assert view.provider_id == "p1"
    with pytest.raises(NotFound):
        new(uow, ico="00305871", provider_id="p9")


def test_the_permission_is_checked_first(uow):
    grants = Grants(provider={(Permission.CUSTOMERS_CREATE, "p1")})
    ctx = RequestContext(request_id="r1", actor_id="u1", policy=grants)
    with pytest.raises(PermissionDenied):
        create_customer(ctx, uow, CreateCustomer(CustomerIdentity("x", "bad")))
    with pytest.raises(PermissionDenied):
        create_customer(ctx, uow, CreateCustomer(CustomerIdentity("x", "bad"), provider_id="p2"))
    assert grants.asked == [
        (Permission.CUSTOMERS_CREATE, None, None),
        (Permission.CUSTOMERS_CREATE, None, "p2"),
    ]
    assert uow.commits == 0


@pytest.mark.parametrize(
    ("call", "permission"),
    [
        (lambda ctx, uow: get_customer(ctx, uow, "c1"), Permission.CUSTOMER_READ),
        (
            lambda ctx, uow: update_identity(ctx, uow, "c1", CustomerIdentity("x", "1")),
            Permission.CUSTOMER_EDIT_IDENTITY,
        ),
        (
            lambda ctx, uow: update_contact(ctx, uow, "c1", CustomerContact()),
            Permission.CUSTOMER_EDIT_CONTACT,
        ),
        (lambda ctx, uow: delete_customer(ctx, uow, "c1"), Permission.CUSTOMERS_DELETE),
        (lambda ctx, uow: restore_customer(ctx, uow, "c1"), Permission.CUSTOMERS_DELETE),
        (lambda ctx, uow: get_parameters(ctx, uow, "c1", 2026), Permission.CUSTOMER_READ),
        (lambda ctx, uow: set_parameters(ctx, uow, "c1", 2026, {}), Permission.CODELISTS_EDIT),
    ],
)
def test_each_use_case_checks_its_permission_in_the_customer(uow, call, permission):
    grants = Grants()
    with pytest.raises(PermissionDenied):
        call(RequestContext(request_id="r1", actor_id="u1", policy=grants), uow)
    assert grants.asked == [(permission, "c1", None)]


def test_contact_changes_need_no_identity_permission(uow):
    boldog = new(uow)
    ctx = RequestContext(
        request_id="r1",
        actor_id="u1",
        policy=Grants(customer={(Permission.CUSTOMER_EDIT_CONTACT, boldog.id)}),
    )
    view = update_contact(ctx, uow, boldog.id, CustomerContact(iban="SK3112000000198742637541"))
    assert view.iban == "SK3112000000198742637541"


def test_parameters_per_year(uow):
    boldog = new(uow)
    set_parameters(SYSTEM, uow, boldog.id, 2026, VALUES)
    assert get_parameters(SYSTEM, uow, boldog.id, 2026).values == VALUES
    with pytest.raises(NotFound):
        get_parameters(SYSTEM, uow, boldog.id, 2027)
    with pytest.raises(ValidationFailed):
        set_parameters(SYSTEM, uow, boldog.id, 2027, {**VALUES, "default_dal": "321"})
    with pytest.raises(NotFound):
        set_parameters(SYSTEM, uow, "nobody", 2026, VALUES)
    assert uow.parameters.years(boldog.id) == [2026]
    assert isinstance(uow.parameters.get(boldog.id, 2026), CustomerParameters)


def test_a_failed_command_leaves_nothing_behind(uow):
    boldog = new(uow)
    with pytest.raises(Conflict), uow:
        customer = uow.customers.get(boldog.id)
        customer.assign_variable_number("1")
        uow.customers.save(customer)
        raise Conflict("boom")
    assert uow.customers.get(boldog.id).variable_number is None


def test_every_write_is_audited_in_the_customer(uow):
    boldog = new(uow)
    update_contact(SYSTEM, uow, boldog.id, CustomerContact(iban="SK3112000000198742637541"))
    update_identity(
        SYSTEM, uow, boldog.id, CustomerIdentity("Obec Boldog", "00305863", "2021009530")
    )
    set_parameters(SYSTEM, uow, boldog.id, 2026, VALUES)
    delete_customer(SYSTEM, uow, boldog.id)
    restore_customer(SYSTEM, uow, boldog.id)
    assert uow.audit.actions() == [
        "customer.created",
        "customer.contact_updated",
        "customer.identity_updated",
        "customer.parameters_set",
        "customer.deleted",
        "customer.restored",
    ]
    assert {e["customer_id"] for e in uow.audit.entries} == {boldog.id}
    assert uow.audit.entries[1]["details"] == {"fields": ["iban"]}
    assert uow.audit.entries[2]["details"] == {"fields": ["dic"]}
    with pytest.raises(Conflict):
        new(uow)  # refused: nothing more is recorded
    assert len(uow.audit.entries) == 6


def test_removing_a_provider_with_the_fakes(uow):
    from riso.tenancy.application import create_provider, remove_provider
    from riso.tenancy.application.ports import LoginRef

    provider = create_provider(SYSTEM, uow, "Účtovníctvo Vzor, s.r.o.", "00305871")
    a = new(uow, provider_id=provider.id)
    b = new(uow, ico="00305880", name="Obec Druhá", provider_id=provider.id)
    staff = LoginRef("u1", "Peter", "p@vzor.sk", "provider_staff", True, "active", False)
    uow.logins.rows.append(("provider", provider.id, staff))
    remove_provider(SYSTEM, uow, provider.id)
    assert uow.customers.get(a.id).provider_id is None
    assert uow.customers.get(b.id).provider_id is None
    assert uow.logins.staff_of([provider.id]) == {provider.id: []}
    assert uow.audit.actions()[-1] == "provider.removed"
    assert uow.audit.entries[-1]["details"] == {"customers": 2, "staff": 1}
