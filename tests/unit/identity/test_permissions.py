"""The role → permission mapping, checked against plan §5.2 row by row.

Each row of the plan's table is written out here as the plan states it, with the
permissions that implement it. A cell is "–" (no access) or a scope word ("✓", "own",
"assigned", "all", "for the customer", "own provider" …): any non-"–" cell means the role
holds the row's permissions for that role. Where a row splits by scope (mapping templates),
each scope has its own permission and only the named role holds it, apart from the admin,
who holds every permission. Where the role may act ("assigned", "own provider") is the
access policy's job (P2-M1-T06), not this mapping's.
"""

import pytest

from riso.identity.domain import ROLE_PERMISSIONS, ROLE_SCOPE, Permission, Role, ScopeKind

P = Permission
VIEWER, USER, STAFF, ADMIN = (
    Role.CUSTOMER_VIEWER,
    Role.CUSTOMER_USER,
    Role.PROVIDER_STAFF,
    Role.PLATFORM_ADMIN,
)

# (capability as in plan §5.2, permissions, cells for viewer, user, provider staff, admin)
PLAN_5_2 = [
    (
        "See dashboard, invoices, code lists, number series, parameters, files",
        [P.CUSTOMER_READ],
        ("✓", "✓", "assigned", "all"),
    ),
    (
        "Upload, check, code, book, discard invoices; mark paid; export",
        [P.INVOICES_PROCESS],
        ("–", "✓", "assigned", "all"),
    ),
    (
        "Import and edit code lists; edit parameters, conventions, number series",
        [P.CODELISTS_EDIT],
        ("–", "✓", "assigned", "all"),
    ),
    ("Use mapping templates", [P.TEMPLATES_USE], ("–", "✓", "✓", "✓")),
    (
        "Create mapping templates (for the customer)",
        [P.TEMPLATES_CREATE_CUSTOMER],
        ("–", "for the customer", "–", "all"),
    ),
    (
        "Create mapping templates (for the provider)",
        [P.TEMPLATES_CREATE_PROVIDER],
        ("–", "–", "for the provider", "all"),
    ),
    (
        "Create mapping templates (global)",
        [P.TEMPLATES_CREATE_GLOBAL],
        ("–", "–", "–", "global"),
    ),
    (
        "Edit own name, login email (verified), notification email, password",
        [P.ACCOUNT_OWN],
        ("own", "own", "own", "own"),
    ),
    (
        "Edit the customer's address and bank account",
        [P.CUSTOMER_EDIT_CONTACT],
        ("–", "✓", "assigned", "all"),
    ),
    (
        # Plan §2 decision 50: name, IČO and DIČ are edited by staff and admins only.
        "Edit the customer's name, IČO and DIČ",
        [P.CUSTOMER_EDIT_IDENTITY],
        ("–", "–", "assigned", "all"),
    ),
    (
        "Assign the customer's variable number",
        [P.CUSTOMER_ASSIGN_VARIABLE_NUMBER],
        ("–", "–", "assigned", "all"),
    ),
    (
        "Invite, deactivate and reactivate a customer's logins; send a reset link",
        [P.LOGINS_MANAGE],
        ("–", "–", "assigned", "all"),
    ),
    (
        "Create a customer, new or as a copy",
        [P.CUSTOMERS_CREATE],
        ("–", "–", "into own provider", "✓"),
    ),
    (
        "Provider overview dashboard and user list",
        [P.PROVIDER_OVERVIEW],
        ("–", "–", "own provider", "all providers"),
    ),
    (
        "Create and remove service providers; add staff; assign and unassign customers",
        [P.PROVIDERS_MANAGE],
        ("–", "–", "–", "✓"),
    ),
    (
        "Delete (soft) and purge customers and users",
        [P.CUSTOMERS_DELETE, P.USERS_DELETE],
        ("–", "–", "–", "✓"),
    ),
    (
        # Plan §10.9: lock and unlock, force logout.
        "Lock and unlock users, force a logout",
        [P.USERS_ADMINISTER],
        ("–", "–", "–", "✓"),
    ),
    ("Impersonate a user (not another admin)", [P.USERS_IMPERSONATE], ("–", "–", "–", "✓")),
    (
        "Global code lists, audit log, jobs, mail outbox, evaluation, data export per customer",
        [
            P.GLOBAL_CODELISTS,
            P.AUDIT_READ,
            P.JOBS_MANAGE,
            P.OUTBOX_READ,
            P.EVALUATION_READ,
            P.CUSTOMER_DATA_EXPORT,
        ],
        ("–", "–", "–", "✓"),
    ),
]

ROLES = (VIEWER, USER, STAFF, ADMIN)
CASES = [
    pytest.param(role, permissions, cells[i], id=f"{role.value}: {capability}")
    for capability, permissions, cells in PLAN_5_2
    for i, role in enumerate(ROLES)
]


@pytest.mark.parametrize(("role", "permissions", "cell"), CASES)
def test_each_row_of_plan_5_2(role, permissions, cell):
    held = ROLE_PERMISSIONS[role]
    for permission in permissions:
        assert (permission in held) is (cell != "–"), (permission, cell)


def test_the_table_covers_every_permission():
    named = {p for _, permissions, _ in PLAN_5_2 for p in permissions}
    assert named == set(Permission)


def test_the_admin_holds_every_permission():
    assert ROLE_PERMISSIONS[ADMIN] == frozenset(Permission)


def test_every_role_has_a_mapping_and_a_scope():
    assert set(ROLE_PERMISSIONS) == set(Role)
    assert ROLE_SCOPE == {
        VIEWER: ScopeKind.CUSTOMER,
        USER: ScopeKind.CUSTOMER,
        STAFF: ScopeKind.PROVIDER,
        ADMIN: ScopeKind.PLATFORM,
    }


def test_the_viewer_can_only_read():
    assert ROLE_PERMISSIONS[VIEWER] == {P.CUSTOMER_READ, P.ACCOUNT_OWN}


def test_permissions_are_plain_strings_for_the_request_context():
    # riso.shared cannot import the enum; a StrEnum passes as its value.
    assert P.CUSTOMER_READ == "customer.read"
    assert all(isinstance(p, str) and "." in p for p in Permission)
