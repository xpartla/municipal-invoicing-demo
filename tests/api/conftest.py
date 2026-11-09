"""API fixtures: the app on a migrated temporary database, with a frozen clock and a fast
password hasher, and a client that sends the CSRF header like the SPA does."""

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from riso.api import Settings, create_app
from riso.api.composition import build_services
from riso.identity.infrastructure.hashing import Argon2Hasher
from riso.platform import Settings as PlatformSettings
from riso.platform.migrations import upgrade
from riso.shared import FixedClock
from tests.factories import PASSWORD

T0 = datetime(2026, 6, 11, 8, 0, tzinfo=UTC)
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


class ApiClient(TestClient):
    """Sends the `riso_csrf` cookie's value as `X-CSRF-Token` on unsafe requests, unless
    `csrf=False`."""

    def request(self, method, url, *args, csrf: bool = True, **kwargs):  # type: ignore[override]
        headers = dict(kwargs.pop("headers", None) or {})
        if csrf and method.upper() in UNSAFE and "X-CSRF-Token" not in headers:
            token = self.cookies.get("riso_csrf")
            if token is None:
                self.get("/api/me")  # any response sets the CSRF cookie
                token = self.cookies.get("riso_csrf")
            headers["X-CSRF-Token"] = token or ""
        kwargs["headers"] = headers
        return super().request(method, url, *args, **kwargs)

    def post(self, url, *args, csrf: bool = True, **kwargs):  # type: ignore[override]
        return self.request("POST", url, *args, csrf=csrf, **kwargs)

    def put(self, url, *args, csrf: bool = True, **kwargs):  # type: ignore[override]
        return self.request("PUT", url, *args, csrf=csrf, **kwargs)

    def patch(self, url, *args, csrf: bool = True, **kwargs):  # type: ignore[override]
        return self.request("PATCH", url, *args, csrf=csrf, **kwargs)

    def delete(self, url, *args, csrf: bool = True, **kwargs):  # type: ignore[override]
        return self.request("DELETE", url, *args, csrf=csrf, **kwargs)

    def login(self, email: str, password: str = PASSWORD):
        response = self.post("/api/auth/login", json={"email": email, "password": password})
        assert response.status_code == 200, response.text
        return response.json()


@pytest.fixture
def clock():
    return FixedClock(T0)


@pytest.fixture(scope="session")
def migrated_file(tmp_path_factory) -> Path:
    """A database migrated to head once per test session; each test gets a copy."""
    path = tmp_path_factory.mktemp("template") / "riso.db"
    upgrade(f"sqlite:///{path}")
    assert (
        not path.with_name("riso.db-wal").exists()
        or path.with_name("riso.db-wal").stat().st_size == 0
    )
    return path


@pytest.fixture
def services(tmp_path, clock, migrated_file):
    settings = PlatformSettings(var_dir=tmp_path / "var", env="test")
    settings.var_dir.mkdir(parents=True)
    shutil.copyfile(migrated_file, settings.var_dir / "riso.db")
    services = build_services(settings, clock=clock, hasher=Argon2Hasher.fast())
    yield services
    services.close()


@pytest.fixture
def app(services, tmp_path):
    return create_app(
        Settings(var_dir=tmp_path / "var", platform=services.settings, run_worker=False),
        services=services,
    )


@pytest.fixture
def client(app):
    return ApiClient(app)


@pytest.fixture
def new_client(app):
    """Another browser, optionally from another address."""

    def make(ip: str = "testclient") -> ApiClient:
        return ApiClient(app, client=(ip, 50000))

    return make


SEED_PASSWORD = "Ukážkové-heslo-2026"


@pytest.fixture(scope="module")
def seeded(tmp_path_factory):
    """The app on a database `riso seed` filled: Boldog with its lists, parameters and
    conventions, the global lists, a login per role. (app, the seed's result, var dir)."""
    from riso.api.seed import seed

    settings = PlatformSettings(var_dir=tmp_path_factory.mktemp("seeded") / "var", env="test")
    done = seed(settings, password=SEED_PASSWORD, hasher=Argon2Hasher.fast())
    services = build_services(settings, hasher=Argon2Hasher.fast())
    app = create_app(
        Settings(var_dir=settings.var_dir, platform=settings, run_worker=False), services=services
    )
    yield app, done, settings.var_dir
    services.close()


@pytest.fixture
def login(seeded):
    """A client logged in as a seeded user: `login("user")`, `login("viewer")` …"""
    app, done, _ = seeded

    def make(key: str) -> ApiClient:
        client = ApiClient(app)
        client.login(done.users[key][1], SEED_PASSWORD)
        return client

    return make


@pytest.fixture(scope="session")
def seeded_template(tmp_path_factory):
    """A var directory `riso seed` filled once, copied by `fresh`."""
    from riso.api.seed import seed

    settings = PlatformSettings(var_dir=tmp_path_factory.mktemp("template") / "var", env="test")
    done = seed(settings, password=SEED_PASSWORD, hasher=Argon2Hasher.fast())
    return settings.var_dir, done


class Fresh:
    """A seeded app of its own, for tests that change invoices, numbers or memory."""

    def __init__(self, app, services, done) -> None:
        self.app, self.services, self.done = app, services, done
        self.boldog = done.customers["Obec Boldog"]

    def login(self, key: str) -> ApiClient:
        client = ApiClient(self.app)
        client.login(self.done.users[key][1], SEED_PASSWORD)
        return client


@pytest.fixture
def fresh(seeded_template, tmp_path):
    source, done = seeded_template
    var_dir = tmp_path / "var"
    shutil.copytree(source, var_dir)
    settings = PlatformSettings(var_dir=var_dir, env="test")
    services = build_services(settings, hasher=Argon2Hasher.fast())
    app = create_app(
        Settings(var_dir=var_dir, platform=settings, run_worker=False), services=services
    )
    yield Fresh(app, services, done)
    services.close()
