"""Impersonation and the audit (plan §5.4, decisions 5–6): starting, writing as the user with
both IDs in the audit, the refused targets and roles, the 60-minute limit, and the blocked
credential endpoints. Also a staff member's write audited in the customer."""

from datetime import timedelta

import pytest

from riso.identity.domain import Role
from tests.factories import PASSWORD, make_customer, make_provider, make_user, update_user

ADMIN, JANA, STAFF = "admin@riso.test", "jana@obec-boldog.sk", "peter@vzor.sk"
CONTACT = {"address": {"street": "Boldog 12", "city": "Boldog", "postal_code": "925 28"}}


@pytest.fixture
def ids(services):
    provider = make_provider(services)
    boldog = make_customer(services, provider_id=provider)
    return {
        "provider": provider,
        "boldog": boldog,
        "admin": make_user(services, ADMIN, name="Alena Správcová", role=Role.PLATFORM_ADMIN),
        "other_admin": make_user(services, "druha@riso.test", role=Role.PLATFORM_ADMIN),
        "jana": make_user(services, JANA, role=Role.CUSTOMER_USER, scope_id=boldog),
        "staff": make_user(services, STAFF, role=Role.PROVIDER_STAFF, scope_id=provider),
    }


@pytest.fixture
def admin(client, ids):
    client.login(ADMIN)
    return client


def impersonate(client, user_id, reason="Hlásenie 42: nevidí faktúry"):
    return client.post(f"/api/admin/users/{user_id}/impersonate", json={"reason": reason})


def audit(admin_client, **params):
    return admin_client.get("/api/admin/audit", params=params).json()["items"]


def test_starting_shows_the_user_and_the_banner_data(admin, ids):
    assert impersonate(admin, ids["jana"]).status_code == 204
    me = admin.get("/api/me").json()
    assert me["user"]["id"] == ids["jana"]
    assert me["impersonation"]["real_user_id"] == ids["admin"]
    assert me["impersonation"]["real_user_name"] == "Alena Správcová"
    assert me["impersonation"]["reason"] == "Hlásenie 42: nevidí faktúry"
    assert me["impersonation"]["expires_at"].startswith("2026-06-11T09:00")
    assert me["platform"] == []  # exactly what the user sees
    assert [c["id"] for c in me["customers"]] == [ids["boldog"]]


def test_a_write_while_impersonating_is_audited_with_both_ids(admin, new_client, ids):
    impersonate(admin, ids["jana"])
    assert admin.patch(f"/api/customers/{ids['boldog']}/contact", json=CONTACT).status_code == 200
    auditor = new_client("10.0.0.2")
    auditor.login("druha@riso.test")
    [started] = audit(auditor, action="impersonation.started")
    assert (started["actor_id"], started["real_actor_id"], started["target_id"]) == (
        ids["admin"],
        None,
        ids["jana"],
    )
    assert started["details"]["reason"] == "Hlásenie 42: nevidí faktúry"
    [write] = audit(auditor, action="customer.contact_updated")
    assert (write["actor_id"], write["real_actor_id"], write["customer_id"]) == (
        ids["jana"],
        ids["admin"],
        ids["boldog"],
    )
    assert write["details"] == {"fields": ["address"]}
    assert write["ip"] == "testclient" and write["request_id"]
    mine = {e["action"] for e in audit(auditor, actor_id=ids["admin"])}
    assert {"impersonation.started", "customer.contact_updated", "auth.login"} <= mine


@pytest.mark.parametrize("target", ["admin", "other_admin"])
def test_an_admin_cannot_be_impersonated(admin, ids, target):
    response = impersonate(admin, ids[target])
    assert response.status_code in (403, 409)
    assert admin.get("/api/me").json()["impersonation"] is None


def test_the_target_must_be_able_to_log_in_and_the_reason_is_required(admin, services, ids):
    invited = make_user(services, "nova@obec-boldog.sk", password=None)
    assert impersonate(admin, invited).status_code == 409
    update_user(services, ids["jana"], lambda user, now: user.lock(now))
    assert impersonate(admin, ids["jana"]).status_code == 409
    update_user(services, ids["jana"], lambda user, now: user.unlock())
    assert impersonate(admin, ids["jana"], reason="   ").status_code == 422
    assert impersonate(admin, "nobody").status_code == 404
    assert impersonate(admin, ids["jana"]).status_code == 204
    assert impersonate(admin, ids["staff"]).status_code == 403  # now acting as Jana


@pytest.mark.parametrize("who", [JANA, STAFF])
def test_only_admins_impersonate(client, ids, who):
    client.login(who)
    assert impersonate(client, ids["jana" if who == STAFF else "staff"]).status_code == 403


def test_impersonation_expires_after_an_hour(admin, new_client, clock, ids):
    impersonate(admin, ids["jana"])
    clock.advance(timedelta(minutes=59))
    assert admin.get("/api/me").json()["user"]["id"] == ids["jana"]
    clock.advance(timedelta(minutes=1))
    me = admin.get("/api/me").json()
    assert me["user"]["id"] == ids["admin"] and me["impersonation"] is None
    [expired] = audit(admin, action="impersonation.expired")
    assert (expired["actor_id"], expired["real_actor_id"]) == (ids["jana"], ids["admin"])


def test_the_personal_credential_endpoints_are_blocked(admin, ids):
    impersonate(admin, ids["jana"])
    password = {"current_password": PASSWORD, "new_password": "Iné-heslo-do-obce-2026"}
    assert admin.post("/api/me/password", json=password).status_code == 403
    email = {"new_email": "x@obec-boldog.sk", "current_password": PASSWORD}
    assert admin.post("/api/me/email-change", json=email).status_code == 403
    assert admin.post("/api/auth/logout-all").status_code == 403
    assert admin.get("/api/me").json()["user"]["id"] == ids["jana"]  # nothing changed


def test_ending_it_returns_to_the_admin(admin, ids):
    impersonate(admin, ids["jana"])
    assert admin.post("/api/me/impersonation/end").status_code == 204
    assert admin.get("/api/me").json()["user"]["id"] == ids["admin"]
    [ended] = audit(admin, action="impersonation.ended")
    assert (ended["actor_id"], ended["real_actor_id"], ended["target_id"]) == (
        ids["jana"],
        ids["admin"],
        ids["jana"],
    )
    assert admin.post("/api/me/impersonation/end").status_code == 409


def test_logging_out_ends_the_impersonation_with_the_session(admin, ids):
    impersonate(admin, ids["jana"])
    assert admin.post("/api/auth/logout").status_code == 204
    assert admin.get("/api/me").status_code == 401


def test_a_deleted_target_ends_the_impersonation(admin, services, ids):
    impersonate(admin, ids["jana"])
    update_user(services, ids["jana"], lambda user, now: user.delete(now))
    assert admin.get("/api/me").json()["user"]["id"] == ids["admin"]


# Provider staff in a customer --------------------------------------------------------------


def test_a_staff_write_is_audited_with_the_customer(client, new_client, ids):
    client.login(STAFF)
    assert client.patch(f"/api/customers/{ids['boldog']}/contact", json=CONTACT).status_code == 200
    admin = new_client("10.0.0.3")
    admin.login(ADMIN)
    [event] = audit(admin, customer_id=ids["boldog"], action="customer.contact_updated")
    assert (event["actor_id"], event["real_actor_id"], event["customer_id"]) == (
        ids["staff"],
        None,
        ids["boldog"],
    )
    assert event["target_type"] == "customer" and event["target_id"] == ids["boldog"]
