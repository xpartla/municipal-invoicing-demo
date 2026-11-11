"""The two routes kept from the demo (P2-M4-T10), admin tools since P2-M7 (plan §2 decision
67): `POST /api/admin/code` codes a posted invoice with the committed bundle and the initial
memory, and `GET /api/admin/eval` gives the latest report of `riso eval` (Vyhodnotenie). Moved
here from `tests/test_api.py` and `tests/test_eval.py` when they left the public API."""

import pytest

from riso.dataset import load_cases


@pytest.fixture
def admin(login):
    return login("admin")


def _invoice(case_id: str) -> dict:
    case = next(c for c in load_cases() if c.id == case_id)
    return case.invoice.model_dump(mode="json")


def test_coding_returns_a_proposal(admin):
    response = admin.post("/api/admin/code", json={"invoice": _invoice("anchor-telekom")})

    assert response.status_code == 200
    proposal = response.json()
    assert proposal["document"]["number"] == "FD/144/26"
    assert proposal["budget"][0]["key"] == "632005 41 01 110 000"
    assert proposal["posting"][0]["md"] == "518 003"
    assert proposal["needs_review"] is False


def test_alternatives_carry_the_whole_line(admin):
    proposal = admin.post("/api/admin/code", json={"invoice": _invoice("anchor-telekom")}).json()

    assert proposal["alternatives"]
    for alternative in proposal["alternatives"]:
        assert alternative["md"] and alternative["dal"] and alternative["budget_text"]


def test_coding_rejects_a_malformed_invoice(admin):
    invoice = _invoice("anchor-telekom") | {"handwritten": {"date": "23.6.26"}}

    assert admin.post("/api/admin/code", json={"invoice": invoice}).status_code == 422


def test_coding_needs_reference_data_for_the_customer(admin):
    invoice = _invoice("anchor-telekom")
    invoice["customer"]["ico"] = "00305111"

    assert admin.post("/api/admin/code", json={"invoice": invoice}).status_code == 404


def test_the_evaluation_report_is_run_once_then_served_and_refreshed(admin):
    first = admin.get("/api/admin/eval", params={"split": "anchor"})
    assert first.status_code == 200
    report = first.json()
    assert report["split"] == "anchor" and len(report["cases"]) == 4
    again = admin.get("/api/admin/eval", params={"split": "anchor"})
    assert again.json()["generated_at"] == report["generated_at"]
    assert admin.get("/api/admin/eval", params={"entity": "00305111"}).status_code == 404
    refreshed = admin.get("/api/admin/eval", params={"split": "anchor", "refresh": "true"})
    assert refreshed.status_code == 200


@pytest.mark.parametrize("key", ["staff", "user", "viewer"])
def test_only_admins_evaluate_or_code(login, key):
    client = login(key)
    assert client.get("/api/admin/eval").status_code == 403
    assert client.post("/api/admin/code", json={}).status_code == 403


def test_without_a_login_both_are_refused(seeded):
    from tests.api.conftest import ApiClient

    app, _, _ = seeded
    client = ApiClient(app)
    assert client.get("/api/admin/eval").status_code == 401
    assert client.post("/api/admin/code", json={}).status_code == 401


def test_the_demo_routes_are_gone(admin):
    assert admin.get("/api/eval").status_code == 404
    assert admin.post("/api/code", json={}).status_code == 404
    for path in ("/api/entities", "/api/invoices", "/api/counters/00305863", "/api/feedback"):
        assert admin.get(path).status_code == 404, path
