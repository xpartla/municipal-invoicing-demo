import pytest
from fastapi.testclient import TestClient

from riso.api import Settings, create_app
from riso.dataset import load_cases


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(Settings(var_dir=tmp_path / "var")))


def _invoice(case_id: str) -> dict:
    case = next(c for c in load_cases() if c.id == case_id)
    return case.invoice.model_dump(mode="json")


def test_entities_lists_boldog(client):
    response = client.get("/api/entities")

    assert response.status_code == 200
    assert response.json() == [
        {
            "ico": "00305863",
            "name": "Obec Boldog",
            "bundle_id": "00305863/2026-08",
            "periods": ["2026-08"],
        }
    ]


def test_the_reference_bundle_is_served(client):
    response = client.get("/api/reference/00305863")

    assert response.status_code == 200
    body = response.json()
    assert body["bundle_id"] == "00305863/2026-08"
    assert len(body["budget_positions_expense"]) == 456


def test_an_unknown_entity_is_not_found(client):
    assert client.get("/api/reference/00305111").status_code == 404


def test_the_picker_lists_the_anchor_invoices(client):
    response = client.get("/api/invoices")

    assert response.status_code == 200
    rows = {row["id"]: row for row in response.json()}
    assert set(rows) == {"anchor-accounting", "anchor-dog-shelter", "anchor-dpo", "anchor-telekom"}
    assert rows["anchor-telekom"]["gross"] == 93.71


def test_one_invoice_is_served_without_its_expected_coding(client):
    response = client.get("/api/invoices/anchor-telekom")

    assert response.status_code == 200
    assert response.json()["handwritten"] == {"date": "2026-06-23", "number": "144"}
    assert "expected" not in response.json()
    assert client.get("/api/invoices/nothing").status_code == 404


def test_coding_answers_not_implemented_until_m1(client):
    response = client.post("/api/code", json={"invoice": _invoice("anchor-telekom")})

    assert response.status_code == 501
    assert "M1" in response.json()["detail"]


def test_coding_rejects_a_malformed_invoice(client):
    invoice = _invoice("anchor-telekom") | {"handwritten": {"date": "23.6.26"}}

    assert client.post("/api/code", json={"invoice": invoice}).status_code == 422


def test_coding_needs_reference_data_for_the_customer(client):
    invoice = _invoice("anchor-telekom")
    invoice["customer"]["ico"] = "00305111"

    assert client.post("/api/code", json={"invoice": invoice}).status_code == 404


def test_the_pages_and_vendored_script_are_served(client):
    page = client.get("/")

    assert page.status_code == 200
    assert "Dodávateľské faktúry" in page.text
    for path in ("/proposal.html", "/reference.html", "/eval.html", "/app.js", "/app.css"):
        assert client.get(path).status_code == 200, path
    assert client.get("/vendor/alpine-3.17.4.min.js").status_code == 200
