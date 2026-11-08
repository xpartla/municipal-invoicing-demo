"""The access policy: who reaches which customer, and with which permissions (plan §4.4)."""

import pytest

from riso.identity.application.access import ALL, Grant, MembershipPolicy
from riso.identity.application.ports import CustomerRef, ProviderRef
from riso.identity.domain import ROLE_PERMISSIONS, Permission, Role, ScopeKind
from tests.fakes.identity import FakeDirectory

P = Permission
A = CustomerRef("cA", "Obec Agátová", "00305863", "p1", True)
B = CustomerRef("cB", "Obec Brezová", "00305871", "p2", True)
C = CustomerRef("cC", "Obec Cerová", "00305880", None, True)
GONE = CustomerRef("cX", "Obec Zrušená", "00305898", "p1", False)
DIRECTORY = FakeDirectory(
    [A, B, C, GONE], [ProviderRef("p1", "Vzor", True), ProviderRef("p2", "Agát", True)]
)


def policy(*grants: tuple[ScopeKind, str | None, Role]) -> MembershipPolicy:
    return MembershipPolicy([Grant(*g) for g in grants], DIRECTORY)


VIEWER_A = policy((ScopeKind.CUSTOMER, "cA", Role.CUSTOMER_VIEWER))
USER_A = policy((ScopeKind.CUSTOMER, "cA", Role.CUSTOMER_USER))
STAFF_1 = policy((ScopeKind.PROVIDER, "p1", Role.PROVIDER_STAFF))
ADMIN = policy((ScopeKind.PLATFORM, None, Role.PLATFORM_ADMIN))
NOBODY = policy()


@pytest.mark.parametrize(
    ("who", "customer", "reaches"),
    [
        (VIEWER_A, "cA", True),
        (VIEWER_A, "cB", False),
        (USER_A, "cA", True),
        (USER_A, "cC", False),
        (STAFF_1, "cA", True),  # assigned to p1
        (STAFF_1, "cB", False),  # another provider's
        (STAFF_1, "cC", False),  # unassigned
        (STAFF_1, "cX", False),  # deleted
        (ADMIN, "cA", True),
        (ADMIN, "cC", True),
        (ADMIN, "cX", True),  # admins see deleted customers
        (ADMIN, "nobody", False),
        (NOBODY, "cA", False),
    ],
)
def test_who_reaches_which_customer(who, customer, reaches):
    assert who.can_access_customer(customer) is reaches
    assert bool(who.in_customer(customer)) is reaches


def test_permissions_in_a_customer_follow_the_role():
    assert VIEWER_A.in_customer("cA") == ROLE_PERMISSIONS[Role.CUSTOMER_VIEWER]
    assert USER_A.in_customer("cA") == ROLE_PERMISSIONS[Role.CUSTOMER_USER]
    assert STAFF_1.in_customer("cA") == ROLE_PERMISSIONS[Role.PROVIDER_STAFF]
    assert ADMIN.in_customer("cB") == ALL
    assert USER_A.allows(P.INVOICES_PROCESS, "cA", None)
    assert not VIEWER_A.allows(P.INVOICES_PROCESS, "cA", None)
    assert not USER_A.allows(P.LOGINS_MANAGE, "cA", None)
    assert STAFF_1.allows(P.LOGINS_MANAGE, "cA", None)


def test_a_customer_user_who_is_also_staff_gets_both():
    both = policy(
        (ScopeKind.CUSTOMER, "cA", Role.CUSTOMER_VIEWER),
        (ScopeKind.PROVIDER, "p1", Role.PROVIDER_STAFF),
    )
    assert both.in_customer("cA") == ROLE_PERMISSIONS[Role.PROVIDER_STAFF]


def test_provider_and_platform_scopes():
    assert STAFF_1.allows(P.CUSTOMERS_CREATE, None, "p1")
    assert not STAFF_1.allows(P.CUSTOMERS_CREATE, None, "p2")
    assert not STAFF_1.allows(P.CUSTOMERS_CREATE, None, None)  # the platform is the admin's
    assert not USER_A.allows(P.PROVIDER_OVERVIEW, None, "p1")
    assert ADMIN.allows(P.CUSTOMERS_CREATE, None, None)
    assert ADMIN.allows(P.PROVIDER_OVERVIEW, None, "p2")
    assert ADMIN.on_platform() == ALL and STAFF_1.on_platform() == frozenset()


def test_the_accessible_customers():
    assert [c.id for c in USER_A.accessible_customers()] == ["cA"]
    assert [c.id for c in STAFF_1.accessible_customers()] == ["cA"]
    assert [c.id for c in ADMIN.accessible_customers()] == ["cA", "cB", "cC"]
    assert NOBODY.accessible_customers() == []
    viewer_of_two = policy(
        (ScopeKind.CUSTOMER, "cB", Role.CUSTOMER_VIEWER),
        (ScopeKind.CUSTOMER, "cA", Role.CUSTOMER_USER),
    )
    assert [c.id for c in viewer_of_two.accessible_customers()] == ["cA", "cB"]


def test_each_customer_is_looked_up_once_per_policy():
    directory = FakeDirectory([A])
    p = MembershipPolicy([Grant(ScopeKind.CUSTOMER, "cA", Role.CUSTOMER_USER)], directory)
    for _ in range(3):
        p.allows(P.CUSTOMER_READ, "cA", None)
    assert directory.lookups == ["cA"]
