"""The two routes kept from the demo (P2-M4-T10): `POST /api/code` codes a posted invoice with
the committed bundle and the initial memory, and `GET /api/eval` gives the latest report of
`riso eval`. The demo's other routes were replaced by the invoice API (their tests are in
`tests/api/test_booking_api.py`)."""

import pytest
from fastapi.testclient import TestClient

from riso.api import Settings, create_app
from riso.dataset import load_cases


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    return TestClient(create_app(Settings(var_dir=tmp_path_factory.mktemp("var"))))


def _invoice(case_id: str) -> dict:
    case = next(c for c in load_cases() if c.id == case_id)
    return case.invoice.model_dump(mode="json")


def test_coding_returns_a_proposal(client):
    response = client.post("/api/code", json={"invoice": _invoice("anchor-telekom")})

    assert response.status_code == 200
    proposal = response.json()
    assert proposal["document"]["number"] == "FD/144/26"
    assert proposal["budget"][0]["key"] == "632005 41 01 110 000"
    assert proposal["posting"][0]["md"] == "518 003"
    assert proposal["needs_review"] is False


def test_alternatives_carry_the_whole_line(client):
    proposal = client.post("/api/code", json={"invoice": _invoice("anchor-telekom")}).json()

    assert proposal["alternatives"]
    for alternative in proposal["alternatives"]:
        assert alternative["md"] and alternative["dal"] and alternative["budget_text"]


def test_coding_rejects_a_malformed_invoice(client):
    invoice = _invoice("anchor-telekom") | {"handwritten": {"date": "23.6.26"}}

    assert client.post("/api/code", json={"invoice": invoice}).status_code == 422


def test_coding_needs_reference_data_for_the_customer(client):
    invoice = _invoice("anchor-telekom")
    invoice["customer"]["ico"] = "00305111"

    assert client.post("/api/code", json={"invoice": invoice}).status_code == 404


def test_the_evaluation_report_is_run_once_then_served(client):
    first = client.get("/api/eval", params={"split": "anchor"})
    assert first.status_code == 200
    report = first.json()
    assert report["split"] == "anchor" and len(report["cases"]) == 4
    again = client.get("/api/eval", params={"split": "anchor"})
    assert again.json()["generated_at"] == report["generated_at"]
    assert client.get("/api/eval", params={"entity": "00305111"}).status_code == 404


def test_the_removed_demo_routes_are_gone(client):
    for path in ("/api/entities", "/api/invoices", "/api/counters/00305863", "/api/feedback"):
        assert client.get(path).status_code == 404, path
