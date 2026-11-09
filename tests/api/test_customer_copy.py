"""The copy routes (P2-M3-T06): staff copy one of their customers into their provider, admins
copy any customer into a provider or none, and the wizard follows the copy job at
`/api/customers/{id}/jobs/{job_id}`."""

import pytest

from riso.api import Settings, create_app
from riso.api.composition import build_services
from riso.identity.infrastructure.hashing import Argon2Hasher
from riso.platform import Settings as PlatformSettings
from tests.api.conftest import SEED_PASSWORD, ApiClient

YEAR = 2026


@pytest.fixture
def env(tmp_path, seeded_copy):
    settings = PlatformSettings(var_dir=tmp_path / "var", env="test")
    done = seeded_copy(settings.var_dir)
    services = build_services(settings, hasher=Argon2Hasher.fast())
    app = create_app(
        Settings(var_dir=settings.var_dir, platform=settings, run_worker=False), services=services
    )

    def login(key):
        client = ApiClient(app)
        client.login(done.users[key][1], SEED_PASSWORD)
        return client

    yield services, done, login
    services.close()


def _body(source, **extra):
    return {
        "name": "Obec Kópia",
        "ico": "99900033",
        "address": {"street": "Hlavná 1", "city": "Kópia", "postal_code": "90001"},
        "source_customer_id": source,
        "options": {"year": YEAR},
        **extra,
    }


def test_staff_copy_boldog_and_follow_the_job(env):
    services, done, login = env
    staff = login("staff")
    boldog, provider = done.customers["Obec Boldog"], done.provider_id
    response = staff.post(f"/api/providers/{provider}/customers/copy", json=_body(boldog))
    assert response.status_code == 202, response.text
    body = response.json()
    customer, job_id = body["customer"], body["job_id"]
    assert (customer["name"], customer["ico"], customer["provider_id"]) == (
        "Obec Kópia",
        "99900033",
        provider,
    )
    job_url = f"/api/customers/{customer['id']}/jobs/{job_id}"
    assert staff.get(job_url).json()["status"] == "queued"
    services.worker().run_pending()
    job = staff.get(job_url).json()
    assert (job["kind"], job["status"]) == ("customer_copy", "succeeded")
    assert job["result"]["parameters"] is True and job["result"]["code_lists"]
    lists = staff.get(f"/api/customers/{customer['id']}/codelists", params={"year": YEAR})
    assert lists.status_code == 200, lists.text
    # Inviting the first login is the logins API's, as for any customer.
    invited = staff.post(
        f"/api/customers/{customer['id']}/logins",
        json={"name": "Starosta Kópie", "email": "starosta@kopia.test", "role": "customer_user"},
    )
    assert invited.status_code == 201, invited.text
    # Boldog's own job is not reachable under the copy, nor the copy's under Boldog.
    assert staff.get(f"/api/customers/{boldog}/jobs/{job_id}").status_code == 404


def test_admins_copy_into_any_provider_or_none(env):
    services, done, login = env
    admin = login("admin")
    response = admin.post(
        "/api/admin/customers/copy",
        json=_body(done.customers["Obec Nezávislá"], options={"year": YEAR, "code_lists": False}),
    )
    assert response.status_code == 202, response.text
    assert response.json()["customer"]["provider_id"] is None


@pytest.mark.parametrize(
    ("user", "status"),
    [("user", 404), ("viewer", 404), ("staff", 404)],  # not their provider; not its customer
)
def test_who_may_not_copy(env, user, status):
    _, done, login = env
    client = login(user)
    source = done.customers["Obec Boldog"]
    if user == "staff":  # the unassigned customer is not one of the provider's
        source = done.customers["Obec Nezávislá"]
    response = client.post(f"/api/providers/{done.provider_id}/customers/copy", json=_body(source))
    assert response.status_code == status, response.text


def test_a_copy_with_a_bad_identity_creates_nothing(env):
    services, done, login = env
    staff = login("staff")
    response = staff.post(
        f"/api/providers/{done.provider_id}/customers/copy",
        json=_body(done.customers["Obec Boldog"], ico="99900034"),
    )
    assert response.status_code == 422
    assert services.worker().run_pending() == 0
    taken = staff.post(
        f"/api/providers/{done.provider_id}/customers/copy",
        json=_body(done.customers["Obec Boldog"], ico="00305863"),
    )
    assert taken.status_code == 409
