"""The `Customer` and `ServiceProvider` aggregates: profile values, soft delete and restore,
the purge precondition and the assignment rules."""

from datetime import UTC, datetime

import pytest

from riso.shared import Conflict, Iban, Ico, InvalidState, ValidationFailed
from riso.tenancy.domain import (
    Address,
    Customer,
    CustomerStatus,
    ProviderStatus,
    ServiceProvider,
    parse_dic,
    parse_variable_number,
)

T0 = datetime(2026, 6, 11, 8, 0, tzinfo=UTC)
BOLDOG = Ico("00305863")


def boldog() -> Customer:
    return Customer.create("c1", " Obec  Boldog ", BOLDOG, T0)


def provider(provider_id: str = "p1") -> ServiceProvider:
    return ServiceProvider.create(provider_id, "Účtovníctvo Vzor, s.r.o.", T0)


def test_a_new_customer_is_active_with_a_clean_name():
    customer = boldog()
    assert (customer.name, customer.status, customer.provider_id) == (
        "Obec Boldog",
        CustomerStatus.ACTIVE,
        None,
    )


@pytest.mark.parametrize(
    ("typed", "stored"), [("2021009530", "2021009530"), (" 2021 009 530 ", "2021009530")]
)
def test_dic_is_ten_digits(typed, stored):
    assert parse_dic(typed) == stored


@pytest.mark.parametrize("typed", ["", "123456789", "12345678901", "0123456789", "SK2021009530"])
def test_invalid_dic_is_refused(typed):
    with pytest.raises(ValidationFailed) as caught:
        parse_dic(typed)
    assert caught.value.errors[0].field == "dic"


@pytest.mark.parametrize(("typed", "stored"), [("1", "1"), ("0030 5863", "00305863")])
def test_variable_numbers(typed, stored):
    assert parse_variable_number(typed) == stored


@pytest.mark.parametrize("typed", ["", "12345678901", "12a", "-1"])
def test_invalid_variable_numbers(typed):
    with pytest.raises(ValidationFailed):
        parse_variable_number(typed)


def test_addresses_are_cleaned_and_slovak_postal_codes_checked():
    address = Address.parse(" Boldog  12 ", "Boldog", "925 28")
    assert (address.street, address.city, address.postal_code) == ("Boldog 12", "Boldog", "92528")
    assert address.formatted_postal_code == "925 28"
    assert Address.parse("Hauptstraße 1", "Wien", "1010", "at").country == "AT"
    for street, city, code, country in [
        ("x", "y", "9252", "SK"),
        ("x", "y", "925 281", "SK"),
        ("", "y", "92528", "SK"),
        ("x", "", "92528", "SK"),
        ("x", "y", "92528", "Slovakia"),
    ]:
        with pytest.raises(ValidationFailed):
            Address.parse(street, city, code, country)


def test_profile_changes():
    customer = boldog()
    iban = Iban.parse("SK31 1200 0000 1987 4263 7541")
    customer.update_contact(Address.parse("Boldog 12", "Boldog", "92528"), iban)
    customer.update_identity("Obec Boldog (Senec)", Ico("00305863"), "2021009530")
    customer.assign_variable_number("305863")
    assert (customer.name, customer.dic, customer.iban, customer.variable_number) == (
        "Obec Boldog (Senec)",
        "2021009530",
        iban,
        "305863",
    )


def test_soft_delete_and_restore():
    customer = boldog()
    customer.delete(T0)
    assert (customer.status, customer.deleted_at, customer.active) == (
        CustomerStatus.DELETED,
        T0,
        False,
    )
    for change in (
        lambda c: c.delete(T0),
        lambda c: c.update_contact(None, None),
        lambda c: c.update_identity("x", BOLDOG, None),
        lambda c: c.assign_variable_number("1"),
        lambda c: c.assign_to(provider()),
    ):
        with pytest.raises(InvalidState):
            change(customer)
    customer.restore()
    assert customer.active and customer.deleted_at is None
    with pytest.raises(InvalidState):
        customer.restore()


def test_purging_needs_a_deleted_customer_and_its_ico_typed():
    customer = boldog()
    with pytest.raises(InvalidState):
        customer.confirm_purge("00305863")
    customer.delete(T0)
    with pytest.raises(ValidationFailed) as caught:
        customer.confirm_purge("00305864")
    assert caught.value.errors[0].field == "ico_confirmation"
    customer.confirm_purge(" 0030 5863 ")


def test_a_customer_has_at_most_one_provider():
    customer = boldog()
    customer.assign_to(provider("p1"))
    assert customer.provider_id == "p1"
    with pytest.raises(Conflict):
        customer.assign_to(provider("p2"))
    with pytest.raises(InvalidState):
        customer.assign_to(provider("p1"))
    customer.unassign()
    assert customer.provider_id is None
    with pytest.raises(InvalidState):
        customer.unassign()
    customer.assign_to(provider("p2"))
    assert customer.provider_id == "p2"


def test_a_removed_provider_takes_no_customers():
    removed = provider()
    removed.remove(T0)
    assert (removed.status, removed.removed_at) == (ProviderStatus.REMOVED, T0)
    with pytest.raises(InvalidState):
        boldog().assign_to(removed)
    with pytest.raises(InvalidState):
        removed.remove(T0)
    with pytest.raises(InvalidState):
        removed.rename("x")


def test_a_deleted_customer_keeps_its_provider_until_unassigned():
    customer = boldog()
    customer.assign_to(provider())
    customer.delete(T0)
    assert customer.provider_id == "p1"
    customer.unassign()
    assert customer.provider_id is None
