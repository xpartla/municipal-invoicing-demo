"""The user and customer management API (P2-M1-T08): each endpoint's success and its main
refusals. Who may call which route is the permission matrix's job (`test_permissions.py`);
here the behaviour."""

import re

import pytest

from riso.identity.domain import Role
from tests.factories import PASSWORD, make_customer, make_provider, make_user

ADMIN, STAFF, JANA, IVAN = (
    "admin@riso.test",
    "peter@vzor.sk",
    "jana@obec-boldog.sk",
    "ivan@obec-boldog.sk",
)
IBAN = "SK3112000000198742637541"


@pytest.fixture
def ids(services):
    provider = make_provider(services)
    boldog = make_customer(services, provider_id=provider)
    return {
        "provider": provider,
        "boldog": boldog,
        "admin": make_user(services, ADMIN, name="Alena Správcová", role=Role.PLATFORM_ADMIN),
        "staff": make_user(
            services, STAFF, name="Peter Účtovník", role=Role.PROVIDER_STAFF, scope_id=provider
        ),
        "jana": make_user(services, JANA, role=Role.CUSTOMER_USER, scope_id=boldog),
    }


@pytest.fixture
def admin(new_client, ids):
    client = new_client("10.0.0.1")
    client.login(ADMIN)
    return client


@pytest.fixture
def staff(new_client, ids):
    client = new_client("10.0.0.2")
    client.login(STAFF)
    return client


def mails(admin, to):
    page = admin.get("/api/admin/outbox", params={"to": to}).json()
    return [admin.get(f"/api/admin/outbox/{m['id']}").json() for m in page["items"]]


def token_in(mail):
    return re.search(r"#([A-Za-z0-9_-]+)", mail["body"]).group(1)


# Customers ----------------------------------------------------------------------------------


def test_staff_create_a_customer_in_their_provider(staff, ids):
    body = {"name": "Obec Vzorová Lehota", "ico": "00305871", "iban": IBAN}
    created = staff.post(f"/api/providers/{ids['provider']}/customers", json=body)
    assert created.status_code == 201
    customer = created.json()
    assert (customer["provider_id"], customer["iban"]) == (ids["provider"], IBAN)
    assert staff.get(f"/api/customers/{customer['id']}").status_code == 200  # reachable at once
    duplicate = staff.post(f"/api/providers/{ids['provider']}/customers", json=body)
    assert duplicate.status_code == 409
    invalid = staff.post(
        f"/api/providers/{ids['provider']}/customers", json={"name": "", "ico": "123"}
    )
    assert {e["loc"][-1] for e in invalid.json()["detail"]} == {"name", "ico"}


def test_admins_create_customers_anywhere(admin, ids):
    unassigned = admin.post("/api/admin/customers", json={"name": "Obec Nová", "ico": "00305880"})
    assert unassigned.status_code == 201 and unassigned.json()["provider_id"] is None
    assigned = admin.post(
        "/api/admin/customers",
        json={"name": "Obec Ďalšia", "ico": "00305898", "provider_id": ids["provider"]},
    )
    assert assigned.json()["provider_id"] == ids["provider"]


def test_the_customer_profile_by_role(client, staff, ids):
    client.login(JANA)
    contact = {
        "address": {"street": "Boldog 12", "city": "Boldog", "postal_code": "925 28"},
        "iban": "SK31 1200 0000 1987 4263 7541",
    }
    response = client.patch(f"/api/customers/{ids['boldog']}/contact", json=contact)
    assert response.status_code == 200
    assert response.json()["address"]["postal_code"] == "92528" and response.json()["iban"] == IBAN
    identity = {"name": "Obec Boldog", "ico": "00305863", "dic": "2021009530"}
    assert (
        client.patch(f"/api/customers/{ids['boldog']}/identity", json=identity).status_code == 403
    )
    assert (
        client.put(
            f"/api/customers/{ids['boldog']}/variable-number", json={"variable_number": "305863"}
        ).status_code
        == 403
    )
    assert (
        staff.patch(f"/api/customers/{ids['boldog']}/identity", json=identity).json()["dic"]
        == "2021009530"
    )
    vs = staff.put(
        f"/api/customers/{ids['boldog']}/variable-number", json={"variable_number": "305863"}
    )
    assert vs.json()["variable_number"] == "305863"
    bad = staff.put(
        f"/api/customers/{ids['boldog']}/variable-number", json={"variable_number": "12a"}
    )
    assert bad.status_code == 422
    cleared = staff.put(
        f"/api/customers/{ids['boldog']}/variable-number", json={"variable_number": None}
    )
    assert cleared.json()["variable_number"] is None


def test_delete_restore_and_purge_a_customer(admin, client, services, ids):
    boldog = ids["boldog"]
    assert (
        admin.post(
            f"/api/customers/{boldog}/purge", json={"ico_confirmation": "00305863"}
        ).status_code
        == 409
    )
    assert admin.delete(f"/api/customers/{boldog}").json()["status"] == "deleted"
    client.login(JANA)
    assert client.get(f"/api/customers/{boldog}").status_code == 404
    assert admin.post(f"/api/customers/{boldog}/restore").json()["status"] == "active"
    assert client.get(f"/api/customers/{boldog}").status_code == 200
    admin.delete(f"/api/customers/{boldog}")
    wrong = admin.post(f"/api/customers/{boldog}/purge", json={"ico_confirmation": "00305864"})
    assert wrong.status_code == 422
    assert (
        admin.post(
            f"/api/customers/{boldog}/purge", json={"ico_confirmation": "0030 5863"}
        ).status_code
        == 204
    )
    assert admin.get(f"/api/customers/{boldog}").status_code == 404
    jana = next(u for u in admin.get("/api/admin/users").json()["items"] if u["email"] == JANA)
    assert jana["memberships"] == []  # the purge removed the membership
    purged = admin.get("/api/admin/audit", params={"action": "customer.purged"}).json()["items"]
    assert purged[0]["customer_id"] == boldog  # the audit keeps the customer's ID


# Providers ----------------------------------------------------------------------------------


def test_providers_staff_and_assignments(admin, services, ids):
    created = admin.post("/api/admin/providers", json={"name": "Agát, s.r.o.", "ico": "00305880"})
    assert created.status_code == 201
    agat = created.json()["id"]
    assert admin.post("/api/admin/providers", json={"name": "x", "ico": "1"}).status_code == 422
    staff = admin.post(
        f"/api/admin/providers/{agat}/staff", json={"email": "eva@agat.sk", "name": "Eva Agátová"}
    )
    assert staff.status_code == 201 and staff.json()["new_account"]
    assert mails(admin, "eva@agat.sk")[0]["subject"] == "Pozvánka do riso: Agát, s.r.o."

    other = make_customer(services, "Obec Agátová", "00305898")
    assert (
        admin.put(f"/api/admin/customers/{other}/provider", json={"provider_id": agat}).status_code
        == 200
    )
    again = admin.put(f"/api/admin/customers/{ids['boldog']}/provider", json={"provider_id": agat})
    assert again.status_code == 409  # Boldog has a provider already
    listing = {p["provider"]["id"]: p for p in admin.get("/api/admin/providers").json()}
    assert [c["id"] for c in listing[agat]["customers"]] == [other]
    assert [s["name"] for s in listing[ids["provider"]]["staff"]] == ["Peter Účtovník"]
    assert admin.delete(f"/api/admin/customers/{other}/provider").json()["provider_id"] is None
    assert admin.delete(f"/api/admin/customers/{other}/provider").status_code == 409


def test_removing_a_provider_unassigns_its_customers_and_deactivates_its_staff(admin, staff, ids):
    removed = admin.delete(f"/api/admin/providers/{ids['provider']}")
    assert removed.json()["status"] == "removed"
    assert admin.get(f"/api/customers/{ids['boldog']}").json()["provider_id"] is None
    assert staff.get(f"/api/customers/{ids['boldog']}").status_code == 404
    assert staff.get("/api/me").json()["providers"] == []
    peter = next(u for u in admin.get("/api/admin/users").json()["items"] if u["email"] == STAFF)
    assert [(m["scope_kind"], m["active"]) for m in peter["memberships"]] == [("provider", False)]
    assert admin.get("/api/admin/providers").json() == []
    assert len(admin.get("/api/admin/providers", params={"include_removed": True}).json()) == 1
    [event] = admin.get("/api/admin/audit", params={"action": "provider.removed"}).json()["items"]
    assert event["details"] == {"customers": 1, "staff": 1}
    assert admin.delete(f"/api/admin/providers/{ids['provider']}").status_code == 409


def test_removing_a_staff_member(admin, staff, ids):
    path = f"/api/admin/providers/{ids['provider']}/staff/{ids['staff']}"
    assert admin.delete(path).status_code == 200
    assert staff.get(f"/api/providers/{ids['provider']}").status_code == 404
    assert admin.delete(path).status_code == 404
    back = admin.post(
        f"/api/admin/providers/{ids['provider']}/staff", json={"email": STAFF, "name": "Peter"}
    )
    assert back.status_code == 201 and not back.json()["new_account"]
    assert staff.get(f"/api/providers/{ids['provider']}").status_code == 200


# A customer's logins -------------------------------------------------------------------------


def test_staff_invite_a_login_who_then_logs_in(staff, admin, new_client, ids):
    invited = staff.post(
        f"/api/customers/{ids['boldog']}/logins",
        json={"email": IVAN, "name": "Ivan Čitateľ", "role": "customer_viewer"},
    )
    assert invited.status_code == 201
    assert invited.json()["user"]["status"] == "invited"
    ivan = new_client("10.5.5.5")
    token = token_in(mails(admin, IVAN)[0])
    ivan.post("/api/auth/invitation/accept", json={"token": token, "password": PASSWORD})
    me = ivan.login(IVAN)
    assert me["customers"][0]["permissions"] == ["account.own", "customer.read"]
    bad_role = staff.post(
        f"/api/customers/{ids['boldog']}/logins",
        json={"email": "x@obec.sk", "name": "X", "role": "platform_admin"},
    )
    assert bad_role.status_code == 422
    twice = staff.post(
        f"/api/customers/{ids['boldog']}/logins", json={"email": IVAN, "name": "Ivan"}
    )
    assert twice.status_code == 409


def test_deactivating_and_reactivating_a_login(staff, client, ids):
    client.login(JANA)
    base = f"/api/customers/{ids['boldog']}/logins/{ids['jana']}"
    assert staff.post(f"{base}/deactivate").status_code == 200
    assert client.get(f"/api/customers/{ids['boldog']}").status_code == 404
    assert staff.post(f"{base}/deactivate").status_code == 409
    directory = staff.get(f"/api/providers/{ids['provider']}/customers").json()
    [jana] = [x for x in directory[0]["logins"] if x["user_id"] == ids["jana"]]
    assert jana["active"] is False
    assert staff.post(f"{base}/reactivate").status_code == 200
    assert client.get(f"/api/customers/{ids['boldog']}").status_code == 200
    stranger = f"/api/customers/{ids['boldog']}/logins/{ids['admin']}/deactivate"
    assert staff.post(stranger).status_code == 404  # not a login of this customer


def test_staff_send_a_reset_link_or_a_new_invitation(staff, admin, services, ids):
    reset = staff.post(f"/api/customers/{ids['boldog']}/logins/{ids['jana']}/reset-link")
    assert reset.json() == {"kind": "password_reset"}
    assert mails(admin, JANA)[0]["template"] == "password_reset"
    staff.post(f"/api/customers/{ids['boldog']}/logins", json={"email": IVAN, "name": "Ivan"})
    ivan = next(
        u["id"] for u in admin.get("/api/admin/users").json()["items"] if u["email"] == IVAN
    )
    again = staff.post(f"/api/customers/{ids['boldog']}/logins/{ivan}/reset-link")
    assert again.json() == {"kind": "invitation"}
    assert [m["template"] for m in mails(admin, IVAN)] == ["invitation", "invitation"]
    admin.post(f"/api/admin/users/{ids['jana']}/lock")
    assert (
        staff.post(f"/api/customers/{ids['boldog']}/logins/{ids['jana']}/reset-link").status_code
        == 409
    )


def test_staff_cannot_manage_an_admins_account(staff, services, ids):
    make_user(services, "admin2@riso.test", role=Role.PLATFORM_ADMIN)
    with services.uow() as uow:
        admin2 = next(
            u for u in uow.users.find() if u.email and u.email.value == "admin2@riso.test"
        )
        from riso.identity.domain import MembershipScope

        admin2.grant(
            uow.ids.new(),
            MembershipScope.customer(ids["boldog"]),
            Role.CUSTOMER_USER,
            uow.clock.now(),
        )
        uow.users.save(admin2)
        uow.commit()
    path = f"/api/customers/{ids['boldog']}/logins/{admin2.id}/deactivate"
    assert staff.post(path).status_code == 403


def test_the_directories(staff, admin, services, ids):
    make_customer(services, "Obec Bez Servisu", "00305880")
    mine = staff.get(f"/api/providers/{ids['provider']}/customers").json()
    assert [c["customer"]["name"] for c in mine] == ["Obec Boldog"]
    assert [(x["name"], x["role"]) for x in mine[0]["logins"]] == [
        ("Jana Vzorová", "customer_user")
    ]
    everyone = admin.get("/api/admin/customers").json()
    assert [c["customer"]["name"] for c in everyone] == ["Obec Bez Servisu", "Obec Boldog"]


# Every account (admins) ----------------------------------------------------------------------


def test_locking_unlocking_and_forcing_a_logout(admin, client, ids):
    client.login(JANA)
    assert admin.post(f"/api/admin/users/{ids['jana']}/lock").json()["locked"] is True
    assert client.get("/api/me").status_code == 401
    assert (
        client.post("/api/auth/login", json={"email": JANA, "password": PASSWORD}).status_code
        == 401
    )
    assert admin.post(f"/api/admin/users/{ids['jana']}/lock").status_code == 409
    assert admin.post(f"/api/admin/users/{ids['jana']}/unlock").json()["locked"] is False
    client.login(JANA)
    assert admin.post(f"/api/admin/users/{ids['jana']}/logout").status_code == 204
    assert client.get("/api/me").status_code == 401
    assert admin.post(f"/api/admin/users/{ids['admin']}/lock").status_code == 409  # not oneself


def test_delete_restore_and_purge_a_user(admin, client, ids):
    client.login(JANA)
    assert admin.post(f"/api/admin/users/{ids['jana']}/purge").status_code == 409  # not deleted yet
    assert admin.post(f"/api/admin/users/{ids['jana']}/delete").json()["status"] == "deleted"
    assert client.get("/api/me").status_code == 401
    assert all(u["id"] != ids["jana"] for u in admin.get("/api/admin/users").json()["items"])
    listed = admin.get("/api/admin/users", params={"include_deleted": True}).json()["items"]
    assert any(u["id"] == ids["jana"] for u in listed)
    assert admin.post(f"/api/admin/users/{ids['jana']}/restore").json()["status"] == "active"
    client.login(JANA)
    admin.post(f"/api/admin/users/{ids['jana']}/delete")
    purged = admin.post(f"/api/admin/users/{ids['jana']}/purge").json()
    assert (purged["status"], purged["email"], purged["name"], purged["memberships"]) == (
        "purged",
        None,
        "",
        [],
    )
    assert admin.post(f"/api/admin/users/{ids['jana']}/restore").status_code == 409


def test_listing_users(admin, ids):
    page = admin.get("/api/admin/users", params={"q": "vzor"}).json()
    assert [u["email"] for u in page["items"]] == [JANA, STAFF]  # Vzorová and vzor.sk, by name
    assert page["total"] == 2


# The caller's profile -------------------------------------------------------------------------


def test_the_personal_profile(client, ids):
    client.login(JANA)
    response = client.patch(
        "/api/me", json={"name": "  Jana   Nová ", "notification_email": "Posta@Obec.sk"}
    )
    assert (response.json()["name"], response.json()["notification_email"]) == (
        "Jana Nová",
        "posta@obec.sk",
    )
    kept = client.patch("/api/me", json={"name": "Jana Vzorová"}).json()
    assert kept["notification_email"] == "posta@obec.sk"  # fields not sent stay
    cleared = client.patch("/api/me", json={"notification_email": ""}).json()
    assert cleared["notification_email"] is None
    assert client.patch("/api/me", json={"notification_email": "nie"}).status_code == 422
    assert client.patch("/api/me", json={"name": ""}).status_code == 422


def test_every_write_is_audited(admin, staff, ids):
    staff.put(f"/api/customers/{ids['boldog']}/variable-number", json={"variable_number": "1"})
    staff.post(f"/api/customers/{ids['boldog']}/logins/{ids['jana']}/deactivate")
    admin.post(f"/api/admin/users/{ids['jana']}/lock")
    actions = [e["action"] for e in admin.get("/api/admin/audit").json()["items"]]
    assert actions[:3] == ["user.locked", "login.deactivated", "customer.variable_number_assigned"]
    deactivated = admin.get("/api/admin/audit", params={"action": "login.deactivated"}).json()[
        "items"
    ][0]
    assert (deactivated["actor_id"], deactivated["customer_id"], deactivated["target_id"]) == (
        ids["staff"],
        ids["boldog"],
        ids["jana"],
    )
