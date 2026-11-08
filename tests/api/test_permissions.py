"""The permission matrix (guide §6.5, plan §13.2).

Every API route has a unique name, an entry in `riso/api/permissions_matrix.py`, and exactly
one access dependency that agrees with its entry. The generated test then calls every route
as every role, in their own and in a foreign customer or provider, and checks who gets in:

- 401 for an anonymous caller, 404 for a customer or provider the caller cannot reach (its
  existence does not leak), 403 for a missing permission or a credential change while
  impersonating;
- "allowed" means the request passed the access check. The test stops it there: it overrides
  `get_services`, which route handlers declare after their access dependency, to raise, so no
  handler runs and nothing changes.

Who reaches what is written out below by hand, from plan §4.4 and §5.2, rather than taken
from the policy under test.
"""

from dataclasses import dataclass

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from riso.api import Settings, create_app
from riso.api.deps import ACCESS_TYPES, get_services
from riso.api.permissions_matrix import MATRIX, RouteAccess, Scope, api_routes
from riso.identity.domain import ROLE_PERMISSIONS, MembershipScope, Role
from tests.factories import make_customer, make_provider, make_session, make_user, update_user

ALLOWED = 299


class ProbeReached(Exception):
    """The request got past its access check."""


def test_every_api_route_has_a_unique_name_and_a_matrix_entry(tmp_path):
    routes = api_routes(create_app(Settings(var_dir=tmp_path)))
    names = [route.name for route in routes]
    assert len(names) == len(set(names)), "route names must be unique"
    missing = sorted(
        f"{r.name} ({', '.join(sorted(r.methods))} {r.path})"
        for r in routes
        if r.name not in MATRIX
    )
    assert missing == [], "routes without an entry in riso/api/permissions_matrix.py"


def test_every_matrix_entry_has_a_route(tmp_path):
    names = {route.name for route in api_routes(create_app(Settings(var_dir=tmp_path)))}
    assert sorted(set(MATRIX) - names) == [], "matrix entries without a route"


def test_routes_outside_public_and_self_name_a_permission():
    for name, access in MATRIX.items():
        if access.scope in (Scope.PUBLIC, Scope.SELF):
            assert access.permission is None, name
        else:
            assert access.permission, name


def access_of(route) -> list[RouteAccess]:
    """The access dependencies a route declares, as matrix entries."""
    found = []
    for dependency in route.route.dependant.dependencies:
        call = dependency.call
        if isinstance(call, ACCESS_TYPES):
            found.append(RouteAccess(call.scope, call.permission, call.personal))
    return found


def test_each_route_declares_the_access_of_its_entry(tmp_path):
    for route in api_routes(create_app(Settings(var_dir=tmp_path))):
        if route.name.startswith("legacy."):
            continue  # the demo's routes have no access dependency until P2-M4
        assert access_of(route) == [MATRIX[route.name]], route.name


def test_public_routes_answer_an_anonymous_caller(tmp_path):
    """No 401 or 403 for a caller without a session. An empty body may give 422, and a
    missing path value 404; both mean the route let the caller in."""
    app = create_app(Settings(var_dir=tmp_path))
    client = TestClient(app)
    csrf = {"riso_csrf": "t0k3n"}
    for route in api_routes(app):
        if MATRIX[route.name].scope is not Scope.PUBLIC:
            continue
        path = route.path.replace("{entity}", "00305863").replace("{invoice_id}", "none")
        for method in route.methods:
            if route.name == "legacy.eval":
                continue  # runs the whole evaluation; covered by test_api.py
            client.cookies.update(csrf)
            headers = {"X-CSRF-Token": "t0k3n"}
            status = client.request(method, path, json={}, headers=headers).status_code
            assert status not in (401, 403), (route.name, method, status)


# The generated matrix ----------------------------------------------------------------------


@dataclass(frozen=True)
class World:
    """Two providers, each with one customer, and a session per role."""

    customer_own: str  # A, assigned to provider 1
    customer_foreign: str  # B, assigned to provider 2
    provider_own: str
    provider_foreign: str
    sessions: dict[str, tuple[str, str] | None]


ROLES = [
    "anonymous",
    "viewer",  # Iba na čítanie in A
    "user",  # Používateľ in A
    "staff_owning",  # staff of provider 1, which A is assigned to
    "staff_other",  # staff of provider 2
    "admin",
    "impersonating",  # the admin acting as the user of A
    "deactivated",  # a user of A whose membership was deactivated
]

ROLE_OF = {
    "viewer": Role.CUSTOMER_VIEWER,
    "user": Role.CUSTOMER_USER,
    "staff_owning": Role.PROVIDER_STAFF,
    "staff_other": Role.PROVIDER_STAFF,
    "admin": Role.PLATFORM_ADMIN,
    "impersonating": Role.CUSTOMER_USER,
}
# Which customers ("A" own, "B" foreign) and providers ("1", "2") each role reaches.
REACHES_CUSTOMER = {
    "viewer": {"A"},
    "user": {"A"},
    "staff_owning": {"A"},
    "staff_other": {"B"},
    "admin": {"A", "B"},
    "impersonating": {"A"},
}
REACHES_PROVIDER = {"staff_owning": {"1"}, "staff_other": {"2"}, "admin": {"1", "2"}}


@pytest.fixture
def world(services) -> World:
    p1, p2 = make_provider(services, "Účtovníctvo Vzor, s.r.o."), make_provider(services, "Agát")
    a = make_customer(services, "Obec Agátová", "00305863", p1)
    b = make_customer(services, "Obec Brezová", "00305871", p2)
    ids = {
        "viewer": make_user(services, "viewer@a.test", role=Role.CUSTOMER_VIEWER, scope_id=a),
        "user": make_user(services, "user@a.test", role=Role.CUSTOMER_USER, scope_id=a),
        "staff_owning": make_user(services, "s1@p.test", role=Role.PROVIDER_STAFF, scope_id=p1),
        "staff_other": make_user(services, "s2@p.test", role=Role.PROVIDER_STAFF, scope_id=p2),
        "admin": make_user(services, "admin@riso.test", role=Role.PLATFORM_ADMIN),
        "deactivated": make_user(services, "gone@a.test", role=Role.CUSTOMER_USER, scope_id=a),
    }
    update_user(
        services,
        ids["deactivated"],
        lambda user, now: user.deactivate_membership(MembershipScope.customer(a), now),
    )
    sessions: dict[str, tuple[str, str] | None] = {"anonymous": None}
    for role, user_id in ids.items():
        sessions[role] = make_session(services, user_id)
    sessions["impersonating"] = make_session(services, ids["admin"], impersonate=ids["user"])
    return World(a, b, p1, p2, sessions)


def expected(access: RouteAccess, role: str, target: str) -> int:
    """`target` is "own" or "foreign": A or B for customer routes, 1 or 2 for provider
    routes."""
    if access.scope is Scope.PUBLIC:
        return ALLOWED
    if role == "anonymous":
        return 401
    if access.scope is Scope.SELF:
        return 403 if access.personal and role == "impersonating" else ALLOWED
    held = ROLE_PERMISSIONS[ROLE_OF[role]] if role in ROLE_OF else frozenset()
    if access.scope is Scope.PLATFORM:
        return ALLOWED if access.permission in held and role == "admin" else 403
    if access.scope is Scope.CUSTOMER:
        reached = REACHES_CUSTOMER.get(role, set())
        key = "A" if target == "own" else "B"
    else:
        reached = REACHES_PROVIDER.get(role, set())
        key = "1" if target == "own" else "2"
    if key not in reached:
        return 404
    return ALLOWED if access.permission in held else 403


def test_the_permission_matrix(app, services, world):
    def probe() -> None:
        raise ProbeReached

    async def reached(request: Request, exc: ProbeReached) -> JSONResponse:
        return JSONResponse({"probe": "reached"}, status_code=ALLOWED)

    app.dependency_overrides[get_services] = probe
    app.add_exception_handler(ProbeReached, reached)

    failures, checked = [], 0
    for route in api_routes(app):
        if route.name.startswith("legacy."):
            continue
        access = MATRIX[route.name]
        for target in ("own", "foreign"):
            if target == "foreign" and access.scope not in (Scope.CUSTOMER, Scope.PROVIDER):
                continue
            path = route.path.replace(
                "{customer_id}", world.customer_own if target == "own" else world.customer_foreign
            ).replace(
                "{provider_id}", world.provider_own if target == "own" else world.provider_foreign
            )
            path = path.replace("{", "x").replace("}", "")  # other IDs: never looked up
            for role in ROLES:
                client = TestClient(app)
                session = world.sessions[role]
                if session is None:
                    client.cookies.set("riso_csrf", "anonymous", domain="testserver.local")
                    csrf = "anonymous"
                else:
                    token, csrf = session
                    client.cookies.set("riso_session", token, domain="testserver.local")
                    client.cookies.set("riso_csrf", csrf, domain="testserver.local")
                for method in sorted(route.methods):
                    status = client.request(
                        method, path, json={}, headers={"X-CSRF-Token": csrf}
                    ).status_code
                    want = expected(access, role, target)
                    checked += 1
                    if status != want:
                        failures.append(
                            f"{route.name} {method} {target} as {role}: {status}, want {want}"
                        )
    assert failures == []
    assert checked >= 100
