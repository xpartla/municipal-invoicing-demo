"""The app frame: error mapping, security headers, the request ID, the pages and the SPA
fallback, and the worker lifespan."""

import time
import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from riso.api import Settings, create_app
from riso.api.frontend import NOT_BUILT
from riso.api.middleware import CSP_DOCS, CSP_STRICT
from riso.jobs import JobStatus
from riso.platform import Settings as PlatformSettings
from riso.platform.migrations import upgrade
from riso.shared import (
    Conflict,
    FieldError,
    InvalidState,
    NotFound,
    PermissionDenied,
    ValidationFailed,
)


def raiser(exc: Exception):
    def endpoint() -> None:
        raise exc

    return endpoint


class Thing(BaseModel):
    name: str
    count: int


@pytest.fixture
def app(tmp_path):
    app = create_app(Settings(var_dir=tmp_path / "var"))
    errors = {
        "not-found": NotFound("no invoice i1"),
        "denied": PermissionDenied("invoice.book denied in customer c1"),
        "conflict": Conflict("number FD/144/26 is used"),
        "invalid-state": InvalidState("invoice i1 is booked"),
        "invalid": ValidationFailed(
            "invalid invoice",
            [FieldError("lines.0.amount", "must be positive", "positive"), FieldError("vs", "x")],
        ),
        "invalid-bare": ValidationFailed("invalid invoice"),
        "crash": RuntimeError("bug"),
    }
    for path, exc in errors.items():
        app.add_api_route(f"/api/test/{path}", raiser(exc), name=f"test.{path}")

    def create(thing: Thing) -> Thing:
        return thing

    app.add_api_route("/api/test/things", create, methods=["POST"], name="test.things")
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.mark.parametrize(
    ("path", "status", "code", "detail"),
    [
        ("not-found", 404, "not_found", "no invoice i1"),
        ("denied", 403, "permission_denied", "invoice.book denied in customer c1"),
        ("conflict", 409, "conflict", "number FD/144/26 is used"),
        ("invalid-state", 409, "invalid_state", "invoice i1 is booked"),
    ],
)
def test_each_domain_error_maps_to_its_status(client, path, status, code, detail):
    response = client.get(f"/api/test/{path}")
    assert response.status_code == status
    assert response.json() == {"detail": detail, "code": code}


def test_a_validation_failure_lists_its_fields_like_fastapi_does(client):
    response = client.get("/api/test/invalid")
    assert response.status_code == 422
    assert response.json() == {
        "code": "validation_failed",
        "detail": [
            {"loc": ["body", "lines", 0, "amount"], "msg": "must be positive", "type": "positive"},
            {"loc": ["body", "vs"], "msg": "x", "type": "invalid"},
        ],
    }
    bare = client.get("/api/test/invalid-bare").json()
    assert bare["detail"] == [
        {"loc": ["body"], "msg": "invalid invoice", "type": "validation_failed"}
    ]


def test_fastapi_request_validation_has_the_same_item_shape(client):
    response = client.post("/api/test/things", json={"name": "x", "count": "many"})
    assert response.status_code == 422
    [item] = response.json()["detail"]
    assert item["loc"] == ["body", "count"]
    assert {"loc", "msg", "type"} <= set(item)


def test_an_unexpected_error_is_a_json_500_with_the_request_id(app):
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/test/crash", headers={"X-Request-ID": "req-123"})
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal Server Error", "request_id": "req-123"}


# --- headers -----------------------------------------------------------------------------


def test_api_responses_carry_the_strict_policy_and_no_caching(client):
    response = client.get("/api/eval", params={"split": "anchor"})
    assert response.status_code == 200
    headers = response.headers
    assert headers["Content-Security-Policy"] == CSP_STRICT
    assert "script-src 'self';" in CSP_STRICT
    assert "unsafe-eval" not in CSP_STRICT
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "same-origin"
    assert "frame-ancestors 'none'" in CSP_STRICT
    assert headers["Cache-Control"] == "no-store"


def test_the_api_docs_get_their_own_policy(client):
    response = client.get("/docs")
    assert response.status_code == 200
    assert response.headers["Content-Security-Policy"] == CSP_DOCS


def test_errors_carry_the_headers_too(client):
    response = client.get("/api/test/not-found")
    assert response.headers["Content-Security-Policy"] == CSP_STRICT
    assert response.headers["X-Frame-Options"] == "DENY"


# --- request ID --------------------------------------------------------------------------


def test_a_well_formed_request_id_is_kept(client):
    response = client.get("/openapi.json", headers={"X-Request-ID": "abc-123.x_y"})
    assert response.headers["X-Request-ID"] == "abc-123.x_y"


@pytest.mark.parametrize("sent", [None, "has spaces", "x" * 65, "a/b", "<script>"])
def test_otherwise_a_new_request_id_is_made(client, sent):
    headers = {"X-Request-ID": sent} if sent else {}
    made = client.get("/openapi.json", headers=headers).headers["X-Request-ID"]
    assert uuid.UUID(made).version == 7


# --- API 404s and the pages without a SPA --------------------------------------------------


@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
def test_an_unknown_api_path_is_a_json_404(client, method):
    response = client.request(method, "/api/no/such/route")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
    assert response.headers["Content-Type"] == "application/json"


def test_a_known_api_path_with_another_method_is_405(client):
    assert client.get("/api/code").status_code == 405


def test_without_a_spa_a_page_says_how_to_build_it(client):
    for path in ("/", "/c/123/invoices", "/proposal.html"):
        response = client.get(path)
        assert (response.status_code, response.text) == (503, NOT_BUILT), path
        assert response.headers["Content-Security-Policy"] == CSP_STRICT


# --- with the SPA --------------------------------------------------------------------------

SPA_INDEX = '<!doctype html><html lang="sk"><div id="root"></div></html>'


@pytest.fixture
def spa(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(SPA_INDEX, encoding="utf-8")
    (dist / "assets" / "index-3f9a1c.js").write_text("console.log(1)", encoding="utf-8")
    app = create_app(Settings(var_dir=tmp_path / "var", spa_dir=dist))
    return TestClient(app)


@pytest.mark.parametrize("path", ["/", "/c/0192/invoices", "/admin/providers", "/login"])
def test_client_routes_get_the_spa(spa, path):
    response = spa.get(path)
    assert response.status_code == 200
    assert response.text == SPA_INDEX
    assert response.headers["Cache-Control"] == "no-cache"
    assert response.headers["Content-Security-Policy"] == CSP_STRICT


def test_hashed_assets_are_cached_for_a_year(spa):
    response = spa.get("/assets/index-3f9a1c.js")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "public, max-age=31536000, immutable"


def test_the_demo_pages_are_gone(spa):
    for path in ("/proposal.html", "/app.js", "/vendor/alpine-3.17.4.min.js"):
        assert spa.get(path).status_code == 404, path


def test_missing_files_are_404_not_the_spa(spa):
    assert spa.get("/assets/gone.js").status_code == 404
    assert spa.get("/favicon.ico").status_code == 404


def test_api_404s_are_not_swallowed_by_the_spa(spa):
    response = spa.get("/api/customers/123/nothing")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_only_get_and_head_reach_the_pages(spa):
    assert spa.post("/c/1/invoices").status_code == 405
    assert spa.head("/").status_code == 200


# --- with the database and the worker -------------------------------------------------------


def test_the_app_refuses_to_start_on_an_unmigrated_database(tmp_path):
    app = create_app(Settings(var_dir=tmp_path, platform=PlatformSettings(var_dir=tmp_path)))
    with pytest.raises(RuntimeError, match="riso migrate"), TestClient(app):
        pass


def test_the_lifespan_runs_the_worker_and_stops_it(tmp_path):
    platform = PlatformSettings(var_dir=tmp_path)
    upgrade(platform.db_url)
    app = create_app(Settings(var_dir=tmp_path, platform=platform))
    services = app.state.services
    with TestClient(app):
        [thread] = services._threads
        assert thread.running
        with services.jobs_uow() as uow:
            job_id = uow.queue.enqueue("noop", {})
            uow.commit()
        thread.wake()
        deadline = time.monotonic() + 5
        while True:
            with services.jobs_uow(immediate=False) as uow:
                if uow.jobs.get(job_id).status is JobStatus.SUCCEEDED:
                    break
            assert time.monotonic() < deadline
            time.sleep(0.02)
    assert not thread.running
