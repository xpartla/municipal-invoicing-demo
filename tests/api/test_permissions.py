"""The permission matrix covers every API route (guide §6.5). From P2-M1 this file also
generates the role × route × own/foreign customer checks."""

from fastapi.testclient import TestClient

from riso.api import Settings, create_app
from riso.api.permissions_matrix import MATRIX, Scope, api_routes


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
        if access.scope not in (Scope.PUBLIC, Scope.SELF):
            assert access.permission, name


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
