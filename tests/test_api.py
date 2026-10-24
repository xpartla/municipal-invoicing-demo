import copy

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


def test_the_picker_lists_every_dataset_invoice(client):
    response = client.get("/api/invoices")

    assert response.status_code == 200
    rows = {row["id"]: row for row in response.json()}
    assert {"anchor-accounting", "anchor-dog-shelter", "anchor-dpo", "anchor-telekom"} <= set(rows)
    assert {row["split"] for row in rows.values()} == {"anchor", "seed", "heldout"}
    assert len(rows) == len(load_cases())
    assert rows["anchor-telekom"]["gross"] == 93.71


def test_one_invoice_is_served_without_its_expected_coding(client):
    response = client.get("/api/invoices/anchor-telekom")

    assert response.status_code == 200
    assert response.json()["handwritten"] == {"date": "2026-06-23", "number": "144"}
    assert "expected" not in response.json()
    assert client.get("/api/invoices/nothing").status_code == 404


def test_coding_returns_a_proposal(client):
    response = client.post("/api/code", json={"invoice": _invoice("anchor-telekom")})

    assert response.status_code == 200
    proposal = response.json()
    assert proposal["document"]["number"] == "FD/144/26"
    assert proposal["budget"][0]["key"] == "632005 41 01 110 000"
    assert proposal["posting"][0]["md"] == "518 003"
    assert proposal["needs_review"] is False


def _feedback(proposal: dict, action: str = "accepted", final: dict | None = None) -> dict:
    return {
        "invoice_id": proposal["invoice_id"],
        "bundle_id": proposal["bundle_id"],
        "action": action,
        "proposal": proposal,
        "final": final or _coding(proposal),
    }


def _coding(proposal: dict) -> dict:
    """The proposal's coding, as a copy to edit."""
    return copy.deepcopy({k: proposal[k] for k in ("document", "posting", "budget")})


def test_accepting_a_proposal_makes_a_precedent_and_uses_up_the_number(client):
    invoice = _invoice("anchor-telekom")
    proposal = client.post("/api/code", json={"invoice": invoice}).json()

    receipt = client.post("/api/feedback", json=_feedback(proposal))

    assert receipt.status_code == 200
    body = receipt.json()
    assert body["document_number"] == "FD/144/26"
    assert body["supplier_ico"] == "35763469"
    assert body["precedents"] == 2  # the screenshot's and this one
    log = client.get("/api/feedback").json()
    assert [(row["invoice_id"], row["action"]) for row in log] == [("anchor-telekom", "accepted")]
    again = client.post("/api/code", json={"invoice": invoice}).json()
    assert "FD/144/26 is already used" in again["validation"]["warnings"]


def test_a_correction_is_stored_as_the_accountant_entered_it(client):
    proposal = client.post("/api/code", json={"invoice": _invoice("anchor-telekom")}).json()
    final = _coding(proposal)
    final["budget"][0] |= {
        "key": "632003 41 01 110 001",
        "ek": "632003",
        "analytika": "001",
        "text": "telefon,fax",
    }

    receipt = client.post("/api/feedback", json=_feedback(proposal, "corrected", final))
    recoded = client.post("/api/code", json={"invoice": _invoice("anchor-telekom")}).json()

    assert receipt.status_code == 200
    assert recoded["budget"][0]["key"] == "632003 41 01 110 001"  # the newest precedent


def test_a_correction_must_use_codes_from_the_dictionaries(client):
    proposal = client.post("/api/code", json={"invoice": _invoice("anchor-telekom")}).json()
    final = _coding(proposal)
    final["posting"][0]["md"] = "518 999"

    response = client.post("/api/feedback", json=_feedback(proposal, "corrected", final))

    assert response.status_code == 422
    assert any("518 999" in error for error in response.json()["detail"])
    assert client.get("/api/feedback").json() == []


def test_an_accepted_proposal_cannot_carry_changes(client):
    proposal = client.post("/api/code", json={"invoice": _invoice("anchor-telekom")}).json()
    final = _coding(proposal)
    final["posting"][0]["text"] = "iný text"

    assert (
        client.post("/api/feedback", json=_feedback(proposal, "accepted", final)).status_code == 422
    )


def test_a_picked_position_brings_its_whole_line(client):
    invoice = _invoice("anchor-telekom")

    line = client.post("/api/line", json={"invoice": invoice, "budget_key": "632003 41 09 111 000"})
    unknown = client.post(
        "/api/line", json={"invoice": invoice, "budget_key": "632003 41 09 111 999"}
    )

    assert line.status_code == 200
    assert line.json() | {"why": None} == {
        "budget_key": "632003 41 09 111 000",
        "md": "518 003",
        "dal": "321 000",
        "transfer": None,
        "budget_text": "MŠ - telefon",
        "posting_text": "tel.poplatky",
        "score": 0.0,
        "why": None,
    }
    assert unknown.status_code == 404


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


def test_the_counters_start_from_the_initial_state(client):
    response = client.get("/api/counters/00305863")

    assert response.status_code == 200
    assert response.json() == [
        {
            "series": "FD",
            "year": 2026,
            "last_used": "FD/222/26",
            "next": "FD/223/26",
            "used": ["FD/183/26", "FD/213/26", "FD/215/26", "FD/222/26"],
        },
        {"series": "FDŠJ", "year": 2026, "last_used": None, "next": "FDŠJ/001/26", "used": []},
    ]


def test_feedback_moves_the_counter_past_the_highest_number_used(client):
    for case_id in ("anchor-telekom", "heldout-19-telekom-phone"):
        proposal = client.post("/api/code", json={"invoice": _invoice(case_id)}).json()
        assert client.post("/api/feedback", json=_feedback(proposal)).status_code == 200

    fd = client.get("/api/counters/00305863").json()[0]

    assert fd["last_used"] == "FD/252/26"
    assert fd["next"] == "FD/253/26"
    assert fd["used"] == [
        "FD/144/26",
        "FD/183/26",
        "FD/213/26",
        "FD/215/26",
        "FD/222/26",
        "FD/252/26",
    ]


def test_counters_of_an_unknown_entity_are_not_found(client):
    assert client.get("/api/counters/00305111").status_code == 404


def test_the_pages_and_vendored_script_are_served(client):
    page = client.get("/")

    assert page.status_code == 200
    assert "Dodávateľské faktúry" in page.text
    for path in (
        "/about.html",
        "/proposal.html",
        "/reference.html",
        "/eval.html",
        "/app.js",
        "/app.css",
    ):
        assert client.get(path).status_code == 200, path
    assert client.get("/vendor/alpine-3.17.4.min.js").status_code == 200
