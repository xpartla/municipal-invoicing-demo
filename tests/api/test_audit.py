"""The audit log: every write so far records itself, a failed write records nothing, and the
admin's search."""

import re

import pytest

from riso.identity.domain import Role
from tests.factories import PASSWORD, make_customer, make_user

ADMIN, JANA = "admin@riso.test", "jana@obec-boldog.sk"


@pytest.fixture
def setup(services, new_client):
    boldog = make_customer(services)
    jana = make_user(services, JANA, role=Role.CUSTOMER_USER, scope_id=boldog)
    make_user(services, ADMIN, role=Role.PLATFORM_ADMIN)
    admin = new_client("10.9.9.9")
    admin.login(ADMIN)
    return {"boldog": boldog, "jana": jana, "admin": admin}


def actions(admin, **params):
    return [e["action"] for e in admin.get("/api/admin/audit", params=params).json()["items"]]


def test_logins_logouts_and_failures_are_audited(client, setup):
    client.post("/api/auth/login", json={"email": JANA, "password": "Zlé-heslo-1234"})
    client.post("/api/auth/login", json={"email": "nikto@obec-boldog.sk", "password": "x"})
    client.login(JANA)
    client.post("/api/auth/logout")
    events = setup["admin"].get("/api/admin/audit", params={"action": "auth."}).json()["items"]
    mine = [e for e in events if e["ip"] == "testclient"]
    assert [e["action"] for e in mine] == [
        "auth.logout",
        "auth.login",
        "auth.login_failed",
        "auth.login_failed",
    ]
    logout, login, unknown, wrong = mine
    assert login["actor_id"] == logout["actor_id"] == setup["jana"]
    assert (wrong["actor_id"], wrong["target_id"]) == (None, setup["jana"])
    assert (unknown["actor_id"], unknown["target_id"]) == (None, None)


def test_throttling_is_audited(client, setup):
    for _ in range(6):
        client.post("/api/auth/login", json={"email": JANA, "password": "Zlé-heslo-1234"})
    assert actions(setup["admin"], action="auth.login_throttled") == ["auth.login_throttled"]


def test_the_mail_flows_are_audited(client, services, setup):
    admin = setup["admin"]
    client.post("/api/auth/password-reset", json={"email": JANA})
    client.post("/api/auth/password-reset", json={"email": "nikto@obec-boldog.sk"})
    [mail] = [
        admin.get(f"/api/admin/outbox/{m['id']}").json()
        for m in admin.get("/api/admin/outbox").json()["items"]
    ]
    token = re.search(r"#([A-Za-z0-9_-]+)", mail["body"]).group(1)
    client.post(
        "/api/auth/password-reset/complete", json={"token": token, "password": "Iné-heslo-2026-x"}
    )
    client.login(JANA, "Iné-heslo-2026-x")
    client.post(
        "/api/me/password", json={"current_password": "Iné-heslo-2026-x", "new_password": PASSWORD}
    )
    client.post(
        "/api/me/email-change",
        json={"new_email": "nova@obec-boldog.sk", "current_password": PASSWORD},
    )
    assert actions(admin, action="user.") == [
        "user.email_change_requested",
        "user.password_changed",
        "user.password_reset",
        "user.reset_requested",
    ]
    reset = admin.get("/api/admin/audit", params={"action": "user.password_reset"}).json()["items"][
        0
    ]
    assert reset["actor_id"] == setup["jana"]  # the link proved who it was


def test_a_failed_write_records_nothing(client, setup):
    client.login(JANA)
    bad = client.patch(f"/api/customers/{setup['boldog']}/contact", json={"iban": "SK00 1234"})
    assert bad.status_code == 422
    assert actions(setup["admin"], action="customer.") == []
    good = client.patch(
        f"/api/customers/{setup['boldog']}/contact", json={"iban": "SK3112000000198742637541"}
    )
    assert good.status_code == 200
    assert actions(setup["admin"], customer_id=setup["boldog"]) == ["customer.contact_updated"]


def test_searching_the_audit(client, setup):
    client.login(JANA)
    admin = setup["admin"]
    assert actions(admin, actor_id=setup["jana"]) == ["auth.login"]
    assert admin.get("/api/admin/audit", params={"size": 1}).json()["total"] == 2  # two logins
    assert actions(admin, action="auth.login", since="2026-06-12T00:00:00Z") == []
    assert client.get("/api/admin/audit").status_code == 403
