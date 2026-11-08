"""Logging in and out, session expiry, CSRF and login throttling (plan §5.3)."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from riso.api import Settings, create_app
from riso.identity.domain import Role
from tests.factories import PASSWORD, make_customer, make_user, update_user

EMAIL = "jana@obec-boldog.sk"


@pytest.fixture
def boldog(services):
    return make_customer(services)


@pytest.fixture
def jana(services, boldog):
    return make_user(services, EMAIL, role=Role.CUSTOMER_USER, scope_id=boldog)


def test_a_correct_login(client, jana, boldog):
    response = client.post(
        "/api/auth/login", json={"email": " Jana@Obec-Boldog.SK ", "password": PASSWORD}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["id"] == jana
    assert body["impersonation"] is None
    assert body["platform"] == []
    assert [c["id"] for c in body["customers"]] == [boldog]
    assert "invoices.process" in body["customers"][0]["permissions"]
    assert "logins.manage" not in body["customers"][0]["permissions"]
    cookies = response.headers.get_list("set-cookie")
    session = next(c for c in cookies if c.startswith("riso_session="))
    assert "HttpOnly" in session and "SameSite=lax" in session and "Path=/" in session
    assert "Max-Age=604800" in session
    csrf = next(c for c in cookies if c.startswith("riso_csrf="))
    assert "HttpOnly" not in csrf
    assert client.get("/api/me").json()["user"]["id"] == jana


@pytest.mark.parametrize(
    ("email", "password"),
    [(EMAIL, "Nesprávne-heslo-1"), ("nikto@obec-boldog.sk", PASSWORD), ("not an email", "x")],
)
def test_a_failed_login_says_nothing_more(client, jana, email, password):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 401
    assert response.json() == {"detail": "login failed", "code": "unauthenticated"}
    assert "riso_session" not in response.cookies
    assert client.get("/api/me").status_code == 401


@pytest.mark.parametrize(
    "change",
    [
        lambda user, now: user.lock(now),
        lambda user, now: user.delete(now),
    ],
    ids=["locked", "deleted"],
)
def test_a_locked_or_deleted_user_cannot_log_in(client, services, jana, change):
    update_user(services, jana, change)
    response = client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 401


def test_an_invited_user_without_a_password_cannot_log_in(client, services):
    make_user(services, "nova@obec-boldog.sk", password=None)
    response = client.post("/api/auth/login", json={"email": "nova@obec-boldog.sk", "password": ""})
    assert response.status_code == 401


def test_locking_ends_an_open_session(client, services, jana):
    client.login(EMAIL)
    update_user(services, jana, lambda user, now: user.lock(now))
    assert client.get("/api/me").status_code == 401


def test_the_idle_timeout(client, clock, jana):
    client.login(EMAIL)
    clock.advance(timedelta(hours=7, minutes=59))
    assert client.get("/api/me").status_code == 200  # a request moves the idle limit
    clock.advance(timedelta(hours=7, minutes=59))
    assert client.get("/api/me").status_code == 200
    clock.advance(timedelta(hours=8))
    assert client.get("/api/me").status_code == 401


def test_the_absolute_limit(client, clock, jana):
    client.login(EMAIL)
    for _ in range(27):  # a request every six hours: 6 days and 18 hours
        clock.advance(timedelta(hours=6))
        assert client.get("/api/me").status_code == 200
    clock.advance(timedelta(hours=5, minutes=59))
    assert client.get("/api/me").status_code == 200  # a minute before the week is out
    clock.advance(timedelta(minutes=1))
    assert client.get("/api/me").status_code == 401  # 7 days after the login


def test_the_session_shows_when_it_expires(client, clock, jana):
    me = client.login(EMAIL)
    assert me["session"]["expires_at"].startswith("2026-06-11T16:00")  # idle: 8 hours
    for _ in range(27):
        clock.advance(timedelta(hours=6))
        me = client.get("/api/me").json()
    assert me["session"]["expires_at"].startswith("2026-06-18T08:00")  # absolute: 7 days


# CSRF ------------------------------------------------------------------------------------


def test_every_response_gives_a_csrf_cookie_before_a_login(client):
    response = client.get("/api/me")
    assert response.status_code == 401
    assert response.cookies.get("riso_csrf")
    again = client.get("/api/me")
    assert "riso_csrf" not in again.cookies  # kept once set


def test_a_login_without_the_csrf_header_is_refused(client, jana):
    client.get("/api/me")
    response = client.post(
        "/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, csrf=False
    )
    assert response.status_code == 403
    response = client.post(
        "/api/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        headers={"X-CSRF-Token": "wrong"},
    )
    assert response.status_code == 403


def test_the_csrf_header_must_match_the_session(client, jana):
    client.login(EMAIL)
    assert client.post("/api/auth/logout", csrf=False).status_code == 403
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": "x"}).status_code == 403
    # A forged pair: the cookie and the header agree, but not with the session.
    client.cookies.set("riso_csrf", "forged", domain="testserver.local")
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": "forged"}).status_code == 403
    assert client.get("/api/me").status_code == 200  # still logged in


def test_the_login_rotates_the_csrf_token(client, jana):
    client.get("/api/me")
    before = client.cookies.get("riso_csrf")
    client.login(EMAIL)
    assert client.cookies.get("riso_csrf") not in (None, before)


# Logging out ------------------------------------------------------------------------------


def test_logout_ends_this_session_only(client, new_client, jana):
    client.login(EMAIL)
    other = new_client()
    other.login(EMAIL)
    response = client.post("/api/auth/logout")
    assert response.status_code == 204
    assert client.get("/api/me").status_code == 401
    assert other.get("/api/me").status_code == 200
    assert client.cookies.get("riso_csrf")  # a fresh anonymous token


def test_logout_everywhere(client, new_client, jana):
    client.login(EMAIL)
    others = [new_client(), new_client()]
    for other in others:
        other.login(EMAIL)
    sessions = client.get("/api/me/sessions").json()
    assert len(sessions) == 3
    assert [s["current"] for s in sessions].count(True) == 1
    assert client.post("/api/auth/logout-all").status_code == 204
    for each in (client, *others):
        assert each.get("/api/me").status_code == 401


# Throttling --------------------------------------------------------------------------------


def wrong(client, email=EMAIL):
    return client.post("/api/auth/login", json={"email": email, "password": "Nesprávne-heslo-1"})


def test_throttling_after_five_failures_and_recovering(client, clock, jana):
    for _ in range(4):
        assert wrong(client).status_code == 401
    assert wrong(client).status_code == 401  # the fifth failure starts the block
    blocked = client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"] == "61"
    assert blocked.json()["code"] == "throttled"
    clock.advance(timedelta(seconds=61))
    assert wrong(client).status_code == 401  # the sixth: blocked for two minutes now
    clock.advance(timedelta(seconds=119))
    assert (
        client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code
        == 429
    )
    clock.advance(timedelta(seconds=2))
    client.login(EMAIL)  # recovered; the success resets the count
    for _ in range(4):
        assert wrong(client).status_code == 401
    client.login(EMAIL)


def test_the_block_grows_to_fifteen_minutes(client, clock, jana):
    """After the n-th failure (n ≥ 5) the account waits 1, 2, 4, 8, then 15 minutes. Attempts
    while blocked are refused without being counted."""
    for failures in range(1, 12):
        if failures > 5:
            clock.advance(timedelta(minutes=min(15, 2 ** (failures - 6))))
        assert wrong(client).status_code == 401
        if failures < 5:
            continue
        probe = wrong(client)
        assert probe.status_code == 429
        expected = 60 * min(15, 2 ** (failures - 5))
        assert int(probe.headers["Retry-After"]) == expected + 1


def test_throttling_per_account_from_any_address(new_client, jana):
    for i in range(5):
        assert wrong(new_client(f"10.0.0.{i}")).status_code == 401
    fresh = new_client("10.0.1.1")
    response = fresh.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 429


def test_throttling_per_address_across_accounts(new_client, services, jana):
    attacker = new_client("192.0.2.7")
    for i in range(5):
        assert wrong(attacker, f"user{i}@obec-boldog.sk").status_code == 401
    response = attacker.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 429
    elsewhere = new_client("192.0.2.8")
    assert (
        elsewhere.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code
        == 200
    )


def test_failures_are_forgotten_after_a_day(client, clock, jana):
    for _ in range(5):
        wrong(client)
    clock.advance(timedelta(days=1))
    for _ in range(4):
        assert wrong(client).status_code == 401
    client.login(EMAIL)


def test_the_login_attempts_table_holds_no_typed_email(client, services, jana):
    wrong(client)
    with services.db.connect() as connection:
        keys = [row[0] for row in connection.exec_driver_sql("SELECT key FROM login_attempts")]
    assert keys and all(":" in k and "@" not in k and "obec" not in k for k in keys)


# Without a database ------------------------------------------------------------------------


def test_the_demo_app_without_a_database_answers_503(tmp_path):
    client = TestClient(create_app(Settings(var_dir=tmp_path)))
    client.cookies.set("riso_csrf", "t")
    response = client.post(
        "/api/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        headers={"X-CSRF-Token": "t"},
    )
    assert response.status_code == 503
