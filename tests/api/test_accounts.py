"""Invitations, password resets, password and email changes, all through the outbox, and the
admin's outbox viewer (plan §5.3)."""

import re
from datetime import timedelta

import pytest

from riso.identity.application.accounts import Invite, invite
from riso.identity.domain import Role, ScopeKind
from riso.shared import RequestContext
from tests.factories import PASSWORD, make_customer, make_provider, make_user, update_user

ADMIN = "admin@riso.test"
JANA = "jana@obec-boldog.sk"
NEW_PASSWORD = "Iné-heslo-do-obce-2026"
LINK = re.compile(r"(http://localhost:8001/[a-z-]+)#([A-Za-z0-9_-]+)")


@pytest.fixture
def boldog(services):
    return make_customer(services)


@pytest.fixture
def admin(services, new_client):
    make_user(services, ADMIN, name="Alena Správcová", role=Role.PLATFORM_ADMIN)
    client = new_client("10.9.9.9")
    client.login(ADMIN)
    return client


def outbox(admin, to=None):
    params = {"to": to} if to else {}
    page = admin.get("/api/admin/outbox", params=params).json()
    return [admin.get(f"/api/admin/outbox/{m['id']}").json() for m in page["items"]]


def link_in(message):
    match = LINK.search(message["body"])
    assert match, message["body"]
    return match.group(1), match.group(2)


def invite_jana(services, customer_id, role=Role.CUSTOMER_USER, email=JANA):
    return invite(
        RequestContext.system("test"),
        services.uow(),
        services.directory,
        services.tokens,
        services.links,
        Invite(email, "Jana Vzorová", ScopeKind.CUSTOMER, customer_id, role),
    )


# Invitations ------------------------------------------------------------------------------


def test_an_invitation_end_to_end(client, services, admin, boldog):
    invited = invite_jana(services, boldog)
    assert invited.new_account and invited.user.status == "invited"
    [mail] = outbox(admin, to=JANA)
    assert mail["subject"] == "Pozvánka do riso: Obec Boldog"
    assert mail["template"] == "invitation" and mail["customer_id"] == boldog
    assert "18. 6. 2026 10:00" in mail["body"]  # 7 days, in Bratislava (CEST)
    page, token = link_in(mail)
    assert page == "http://localhost:8001/invitation"

    info = client.post("/api/auth/token-info", json={"token": token}).json()
    assert info["kind"] == "invitation" and info["email"] == JANA and info["name"] == "Jana Vzorová"

    weak = client.post("/api/auth/invitation/accept", json={"token": token, "password": "jana"})
    assert weak.status_code == 422
    assert weak.json()["detail"][0]["loc"] == ["body", "password"]
    done = client.post("/api/auth/invitation/accept", json={"token": token, "password": PASSWORD})
    assert done.status_code == 204
    me = client.login(JANA)
    assert [c["id"] for c in me["customers"]] == [boldog]

    again = client.post("/api/auth/invitation/accept", json={"token": token, "password": PASSWORD})
    assert again.status_code == 422
    assert again.json()["detail"][0]["type"] == "token_invalid"


def test_an_invitation_expires_after_seven_days(client, services, admin, clock, boldog):
    invite_jana(services, boldog)
    _, token = link_in(outbox(admin, to=JANA)[0])
    clock.advance(timedelta(days=7))
    response = client.post(
        "/api/auth/invitation/accept", json={"token": token, "password": PASSWORD}
    )
    assert response.status_code == 422
    assert client.post("/api/auth/token-info", json={"token": token}).status_code == 422


def test_a_new_invitation_replaces_the_old_link(client, services, admin, boldog):
    other = make_customer(services, "Obec Vzorová Lehota", "00305871")
    invite_jana(services, boldog)
    invite_jana(services, other, Role.CUSTOMER_VIEWER)  # still invited: a fresh link
    mails = outbox(admin, to=JANA)
    assert [m["template"] for m in mails] == ["invitation", "invitation"]
    _, newest = link_in(mails[0])
    _, oldest = link_in(mails[1])
    assert client.post("/api/auth/token-info", json={"token": oldest}).status_code == 422
    assert (
        client.post(
            "/api/auth/invitation/accept", json={"token": newest, "password": PASSWORD}
        ).status_code
        == 204
    )
    assert {c["id"] for c in client.login(JANA)["customers"]} == {boldog, other}


def test_inviting_an_existing_account_adds_access_without_a_token(services, admin, boldog):
    make_user(services, JANA)
    invited = invite_jana(services, boldog)
    assert not invited.new_account
    [mail] = outbox(admin, to=JANA)
    assert mail["template"] == "access_granted"
    assert "http://localhost:8001/login" in mail["body"]
    assert "#" not in mail["body"]


def test_inviting_a_deleted_account_is_refused(services, boldog):
    jana = make_user(services, JANA)
    update_user(services, jana, lambda user, now: user.delete(now))
    with pytest.raises(Exception, match="deleted account"):
        invite_jana(services, boldog)


def test_staff_are_invited_into_a_provider(services, admin):
    provider = make_provider(services)
    invite(
        RequestContext.system("test"),
        services.uow(),
        services.directory,
        services.tokens,
        services.links,
        Invite(
            "peter@vzor.sk", "Peter Účtovník", ScopeKind.PROVIDER, provider, Role.PROVIDER_STAFF
        ),
    )
    [mail] = outbox(admin, to="peter@vzor.sk")
    assert mail["subject"] == "Pozvánka do riso: Účtovníctvo Vzor, s.r.o."


# Password reset ---------------------------------------------------------------------------


def test_a_reset_request_answers_the_same_for_unknown_addresses(client, services, admin):
    make_user(services, JANA)
    known = client.post("/api/auth/password-reset", json={"email": JANA})
    unknown = client.post("/api/auth/password-reset", json={"email": "nikto@obec-boldog.sk"})
    malformed = client.post("/api/auth/password-reset", json={"email": "nie je adresa"})
    assert known.status_code == unknown.status_code == malformed.status_code == 202
    assert known.json() == unknown.json() == malformed.json()
    assert [m["to_address"] for m in outbox(admin) if m["template"] == "password_reset"] == [JANA]


@pytest.mark.parametrize(
    "change", [lambda u, now: u.lock(now), lambda u, now: u.delete(now)], ids=["locked", "deleted"]
)
def test_no_reset_mail_for_a_locked_or_deleted_account(client, services, admin, change):
    jana = make_user(services, JANA)
    update_user(services, jana, change)
    assert client.post("/api/auth/password-reset", json={"email": JANA}).status_code == 202
    assert outbox(admin, to=JANA) == []


def test_a_reset_end_to_end_ends_every_session(client, new_client, services, admin):
    make_user(services, JANA)
    elsewhere = new_client("10.1.1.1")
    elsewhere.login(JANA)
    client.post("/api/auth/password-reset", json={"email": JANA})
    [mail] = outbox(admin, to=JANA)
    assert mail["subject"] == "Obnovenie hesla do riso"
    page, token = link_in(mail)
    assert page == "http://localhost:8001/reset-password"
    assert (
        client.post("/api/auth/token-info", json={"token": token}).json()["kind"]
        == "password_reset"
    )
    response = client.post(
        "/api/auth/password-reset/complete", json={"token": token, "password": NEW_PASSWORD}
    )
    assert response.status_code == 204
    assert elsewhere.get("/api/me").status_code == 401
    assert (
        client.post("/api/auth/login", json={"email": JANA, "password": PASSWORD}).status_code
        == 401
    )
    client.login(JANA, NEW_PASSWORD)
    reused = client.post(
        "/api/auth/password-reset/complete", json={"token": token, "password": PASSWORD}
    )
    assert reused.status_code == 422


def test_a_reset_link_lasts_an_hour(client, services, admin, clock):
    make_user(services, JANA)
    client.post("/api/auth/password-reset", json={"email": JANA})
    _, token = link_in(outbox(admin, to=JANA)[0])
    clock.advance(timedelta(minutes=59))
    assert client.post("/api/auth/token-info", json={"token": token}).status_code == 200
    clock.advance(timedelta(minutes=1))
    response = client.post(
        "/api/auth/password-reset/complete", json={"token": token, "password": NEW_PASSWORD}
    )
    assert response.status_code == 422


def test_a_token_of_another_kind_does_not_work(client, services, admin, boldog):
    invite_jana(services, boldog)
    _, token = link_in(outbox(admin, to=JANA)[0])
    response = client.post(
        "/api/auth/password-reset/complete", json={"token": token, "password": NEW_PASSWORD}
    )
    assert response.status_code == 422
    assert client.post("/api/auth/email-change/confirm", json={"token": token}).status_code == 422
    assert client.post("/api/auth/token-info", json={"token": ""}).status_code == 422


# Changing the password --------------------------------------------------------------------


def test_a_password_change_logs_out_the_other_sessions(client, new_client, services, admin):
    make_user(services, JANA)
    client.login(JANA)
    others = [new_client("10.2.2.2"), new_client("10.3.3.3")]
    for other in others:
        other.login(JANA)
    wrong = client.post(
        "/api/me/password", json={"current_password": "zlé-heslo-123", "new_password": NEW_PASSWORD}
    )
    assert wrong.status_code == 422
    assert wrong.json()["detail"][0]["loc"] == ["body", "current_password"]
    weak = client.post(
        "/api/me/password", json={"current_password": PASSWORD, "new_password": "password1234"}
    )
    assert weak.json()["detail"][0] == {
        "loc": ["body", "new_password"],
        "msg": "too common or too simple",
        "type": "password_common",
    }
    done = client.post(
        "/api/me/password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD}
    )
    assert done.status_code == 204
    assert client.get("/api/me").status_code == 200  # this session stays
    for other in others:
        assert other.get("/api/me").status_code == 401
    [notice] = [m for m in outbox(admin, to=JANA) if m["template"] == "password_changed"]
    assert notice["subject"] == "Heslo do riso bolo zmenené"


# Changing the login email -----------------------------------------------------------------


def test_an_email_change_end_to_end(client, services, admin):
    make_user(services, JANA)
    client.login(JANA)
    response = client.post(
        "/api/me/email-change",
        json={"new_email": "Jana.Nova@Obec-Boldog.sk", "current_password": PASSWORD},
    )
    assert response.status_code == 202
    [confirm] = outbox(admin, to="jana.nova@obec-boldog.sk")
    [notice] = outbox(admin, to=JANA)
    assert (
        notice["template"] == "email_change_notice" and "jana.nova@obec-boldog.sk" in notice["body"]
    )
    page, token = link_in(confirm)
    assert page == "http://localhost:8001/confirm-email"
    info = client.post("/api/auth/token-info", json={"token": token}).json()
    assert (info["kind"], info["email"]) == ("email_change", "jana.nova@obec-boldog.sk")
    assert client.get("/api/me").json()["user"]["email"] == JANA  # not yet
    assert client.post("/api/auth/email-change/confirm", json={"token": token}).status_code == 204
    assert client.get("/api/me").json()["user"]["email"] == "jana.nova@obec-boldog.sk"
    assert client.post("/api/auth/email-change/confirm", json={"token": token}).status_code == 422
    client.post("/api/auth/logout")
    client.login("jana.nova@obec-boldog.sk")
    assert (
        client.post("/api/auth/login", json={"email": JANA, "password": PASSWORD}).status_code
        == 401
    )


def test_an_email_change_needs_the_password_and_a_free_address(client, services):
    make_user(services, JANA)
    make_user(services, "ivan@obec-boldog.sk", name="Ivan Čitateľ")
    client.login(JANA)
    wrong = client.post(
        "/api/me/email-change", json={"new_email": "x@obec-boldog.sk", "current_password": "nie"}
    )
    assert wrong.status_code == 422
    taken = client.post(
        "/api/me/email-change",
        json={"new_email": "ivan@obec-boldog.sk", "current_password": PASSWORD},
    )
    assert taken.status_code == 409
    same = client.post(
        "/api/me/email-change", json={"new_email": JANA, "current_password": PASSWORD}
    )
    assert same.status_code == 422
    bad = client.post(
        "/api/me/email-change", json={"new_email": "nie", "current_password": PASSWORD}
    )
    assert bad.json()["detail"][0]["loc"] == ["body", "new_email"]


def test_an_email_change_link_lasts_a_day_and_the_address_must_stay_free(
    client, services, admin, clock
):
    make_user(services, JANA)
    client.login(JANA)
    client.post(
        "/api/me/email-change",
        json={"new_email": "nova@obec-boldog.sk", "current_password": PASSWORD},
    )
    _, token = link_in(outbox(admin, to="nova@obec-boldog.sk")[0])
    make_user(services, "nova@obec-boldog.sk", name="Niekto Iný")  # taken meanwhile
    assert client.post("/api/auth/email-change/confirm", json={"token": token}).status_code == 409
    clock.advance(timedelta(hours=24))
    assert client.post("/api/auth/email-change/confirm", json={"token": token}).status_code == 422


# The outbox viewer ------------------------------------------------------------------------


def test_only_admins_read_the_outbox(client, services, admin, boldog):
    invite_jana(services, boldog)
    assert client.get("/api/admin/outbox").status_code == 401
    make_user(services, "ivan@obec-boldog.sk", role=Role.CUSTOMER_USER, scope_id=boldog)
    client.login("ivan@obec-boldog.sk")
    assert client.get("/api/admin/outbox").status_code == 403
    page = admin.get("/api/admin/outbox").json()
    assert page["total"] == 1 and "body" not in page["items"][0]
    assert admin.get("/api/admin/outbox/nothing").status_code == 404


def test_the_outbox_pages_newest_first(services, admin, clock, boldog):
    for i in range(3):
        invite_jana(services, boldog, email=f"user{i}@obec-boldog.sk")
        clock.advance(timedelta(minutes=1))
    page = admin.get("/api/admin/outbox", params={"size": 2}).json()
    assert page["total"] == 3
    assert [m["to_address"] for m in page["items"]] == [
        "user2@obec-boldog.sk",
        "user1@obec-boldog.sk",
    ]
    rest = admin.get("/api/admin/outbox", params={"size": 2, "page": 2}).json()
    assert [m["to_address"] for m in rest["items"]] == ["user0@obec-boldog.sk"]
    assert admin.get("/api/admin/outbox", params={"size": 201}).status_code == 422
