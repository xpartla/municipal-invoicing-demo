"""The access dependencies end to end: 404 for an unreachable customer or provider, 403 for
a missing permission, deleted customers for admins only, and the request context's acting
customer."""

import pytest

from riso.identity.domain import MembershipScope, Role
from tests.factories import make_customer, make_provider, make_user, update_user


@pytest.fixture
def setup(services):
    p1 = make_provider(services)
    a = make_customer(services, "Obec Agátová", "00305863", p1)
    b = make_customer(services, "Obec Brezová", "00305871")
    make_user(services, "user@a.test", role=Role.CUSTOMER_USER, scope_id=a)
    make_user(services, "staff@p.test", role=Role.PROVIDER_STAFF, scope_id=p1)
    make_user(services, "admin@riso.test", role=Role.PLATFORM_ADMIN)
    return {"p1": p1, "a": a, "b": b}


def test_a_foreign_customer_is_not_found_not_forbidden(client, setup):
    client.login("user@a.test")
    assert client.get(f"/api/customers/{setup['a']}").json()["name"] == "Obec Agátová"
    foreign = client.get(f"/api/customers/{setup['b']}")
    missing = client.get("/api/customers/does-not-exist")
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["code"] == missing.json()["code"] == "not_found"


def test_a_missing_permission_in_a_reachable_scope_is_forbidden(client, setup):
    client.login("user@a.test")
    assert client.get(f"/api/providers/{setup['p1']}").status_code == 404  # not its provider
    client.post("/api/auth/logout")
    client.login("staff@p.test")
    overview = client.get(f"/api/providers/{setup['p1']}").json()
    assert [c["id"] for c in overview["customers"]] == [setup["a"]]
    assert client.get("/api/admin/outbox").status_code == 403


def test_a_deleted_customer_is_reachable_by_admins_only(client, new_client, services, setup):
    def delete(customer_id):
        with services.uow() as uow:
            customer = uow.customers.get(customer_id)
            customer.delete(uow.clock.now())
            uow.customers.save(customer)
            uow.commit()

    delete(setup["a"])
    client.login("user@a.test")
    assert client.get(f"/api/customers/{setup['a']}").status_code == 404
    assert client.get("/api/me").json()["customers"] == []
    admin = new_client("10.0.0.9")
    admin.login("admin@riso.test")
    assert admin.get(f"/api/customers/{setup['a']}").json()["status"] == "deleted"


def test_a_deactivated_membership_loses_the_customer_at_once(client, services, setup):
    user = make_user(services, "ivan@a.test", role=Role.CUSTOMER_VIEWER, scope_id=setup["a"])
    client.login("ivan@a.test")
    assert client.get(f"/api/customers/{setup['a']}").status_code == 200
    update_user(
        services,
        user,
        lambda u, now: u.deactivate_membership(MembershipScope.customer(setup["a"]), now),
    )
    assert client.get(f"/api/customers/{setup['a']}").status_code == 404
    assert client.get("/api/me").status_code == 200  # the login itself still works


def test_the_capabilities_per_role(client, new_client, setup):
    client.login("staff@p.test")
    me = client.get("/api/me").json()
    assert [p["id"] for p in me["providers"]] == [setup["p1"]]
    assert "customers.create" in me["providers"][0]["permissions"]
    assert [c["id"] for c in me["customers"]] == [setup["a"]]
    assert "logins.manage" in me["customers"][0]["permissions"]
    assert me["platform"] == []
    admin = new_client("10.0.0.9")
    admin.login("admin@riso.test")
    me = admin.get("/api/me").json()
    assert {c["id"] for c in me["customers"]} == {setup["a"], setup["b"]}
    assert "users.impersonate" in me["platform"]


def test_the_request_context_carries_the_acting_customer(app, client, setup):
    from typing import Annotated

    from fastapi import Depends

    from riso.api.deps import Caller, customer_context
    from riso.identity.domain import Permission

    seen = {}

    def peek(caller: Annotated[Caller, Depends(customer_context(Permission.CUSTOMER_READ))]):
        seen["ctx"] = caller.ctx
        return {}

    app.add_api_route("/api/customers/{customer_id}/peek", peek, name="test.peek")
    client.login("user@a.test")
    assert client.get(f"/api/customers/{setup['a']}/peek").status_code == 200
    ctx = seen["ctx"]
    assert (ctx.customer_id, ctx.real_actor_id, ctx.ip) == (setup["a"], None, "testclient")
    assert ctx.actor_id and ctx.request_id
