"""`riso seed` (P2-M1-T09): the same state on every `--reset`, the refusals, and a login as
each seeded user."""

import json

import pytest
from sqlalchemy import inspect, text

from riso import paths
from riso.api import Settings, create_app
from riso.api.composition import build_services
from riso.api.seed import USERS, SeedRefused, seed
from riso.cli import main
from riso.identity.infrastructure.hashing import Argon2Hasher
from riso.platform import Database
from riso.platform import Settings as PlatformSettings
from tests.api.conftest import ApiClient

PASSWORD = "Ukážkové-heslo-2026"


@pytest.fixture
def settings(tmp_path):
    return PlatformSettings(var_dir=tmp_path / "var", env="test")


def run(settings, **kwargs):
    return seed(settings, password=PASSWORD, hasher=Argon2Hasher.fast(), **kwargs)


def dump(settings) -> dict[str, list[tuple]]:
    """Every table's rows, ordered, without the salted password hashes."""
    db = Database(settings.db_url)
    try:
        tables = {}
        with db.connect() as connection:
            for name in sorted(inspect(connection).get_table_names()):
                if name == "alembic_version":
                    continue
                columns = [
                    c["name"]
                    for c in inspect(connection).get_columns(name)
                    if c["name"] != "password_hash"
                ]
                rows = connection.execute(
                    text(f"SELECT {', '.join(columns)} FROM {name} ORDER BY 1")
                )
                tables[name] = [tuple(row) for row in rows]
        return tables
    finally:
        db.dispose()


def test_seeding_twice_with_reset_gives_the_same_state(settings):
    first = run(settings)
    before = dump(settings)
    assert len(before["users"]) == 4 and len(before["customers"]) == 3
    second = run(settings, reset=True)
    assert dump(settings) == before
    assert first.customers == second.customers and first.provider_id == second.provider_id


def test_the_seeded_world(settings):
    done = run(settings)
    db = Database(settings.db_url)
    try:
        with db.connect() as c:
            customers = dict(c.execute(text("SELECT name, ico FROM customers")).all())
            assigned = {
                r[0] for r in c.execute(text("SELECT customer_id FROM provider_assignments"))
            }
            roles = sorted(c.execute(text("SELECT role, scope_kind FROM memberships")).all())
            year, zdroj = c.execute(
                text("SELECT year, default_zdroj FROM customer_parameters")
            ).one()
    finally:
        db.dispose()
    assert customers == {
        "Obec Boldog": "00305863",
        "Obec Vzorová Lehota": "99900017",
        "Obec Nezávislá": "99900025",
    }
    assert assigned == {done.customers["Obec Boldog"], done.customers["Obec Vzorová Lehota"]}
    assert roles == [
        ("customer_user", "customer"),
        ("customer_viewer", "customer"),
        ("platform_admin", "platform"),
        ("provider_staff", "provider"),
    ]
    boldog = json.loads((paths.ENTITIES_DIR / "00305863.json").read_text(encoding="utf-8"))
    assert (year, zdroj) == (boldog["budget_year"], boldog["default_zdroj"])
    assert all(email.endswith(".test") for _, email, _ in done.users.values())


@pytest.mark.parametrize("env", [None, "prod"])
def test_the_seed_refuses_outside_dev_and_test(tmp_path, env):
    with pytest.raises(SeedRefused, match="RISO_ENV"):
        run(PlatformSettings(var_dir=tmp_path, env=env))
    assert not (tmp_path / "riso.db").exists()


def test_the_seed_refuses_a_database_with_users(settings):
    run(settings)
    with pytest.raises(SeedRefused, match="--reset"):
        run(settings)


def test_a_weak_seed_password_is_refused(settings):
    with pytest.raises(SeedRefused, match="RISO_SEED_PASSWORD"):
        seed(settings, password="password1234")


def test_generated_passwords_are_shown_once_and_differ(settings):
    done = seed(settings, hasher=Argon2Hasher.fast())
    passwords = [p for _, _, p in done.users.values()]
    assert done.generated_passwords and len(set(passwords)) == 4
    assert all(len(p) >= 12 for p in passwords)


def test_each_seeded_user_logs_in(settings, tmp_path):
    done = run(settings)
    services = build_services(settings, hasher=Argon2Hasher.fast())
    app = create_app(
        Settings(var_dir=settings.var_dir, platform=settings, run_worker=False), services=services
    )
    try:
        seen = {}
        for spec in USERS:
            client = ApiClient(app)
            me = client.login(spec.email, PASSWORD)
            seen[spec.key] = (
                sorted(c["name"] for c in me["customers"]),
                bool(me["platform"]),
                len(me["providers"]),
            )
    finally:
        services.close()
    assert seen == {
        "admin": (["Obec Boldog", "Obec Nezávislá", "Obec Vzorová Lehota"], True, 0),
        "staff": (["Obec Boldog", "Obec Vzorová Lehota"], False, 1),
        "user": (["Obec Boldog"], False, 0),
        "viewer": (["Obec Boldog"], False, 0),
    }
    assert set(done.users) == {"admin", "staff", "user", "viewer"}


def test_the_command(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("RISO_VAR_DIR", str(tmp_path / "var"))
    monkeypatch.setenv("RISO_SEED_PASSWORD", PASSWORD)
    monkeypatch.delenv("RISO_ENV", raising=False)
    assert main(["seed"]) == 2
    assert "RISO_ENV" in capsys.readouterr().err
    monkeypatch.setenv("RISO_ENV", "dev")
    assert main(["seed"]) == 0
    out = capsys.readouterr().out
    assert "admin@riso.test" in out and "(RISO_SEED_PASSWORD)" in out and PASSWORD not in out
    assert main(["seed"]) == 2
    assert main(["seed", "--reset"]) == 0
