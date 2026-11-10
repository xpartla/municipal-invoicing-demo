"""Checking, coding and booking stored invoices (P2-M4-T03). The demo's feedback tests
(`tests/test_api.py`), ported to the invoice routes, plus the numbering rule of plan §2
decision 61 through the API, unbooking, discarding and paying."""

import copy
from datetime import date

import pytest

from riso.audit.infrastructure.log import SqlAuditRecorder
from riso.contracts import Coding
from riso.invoicing.application import BookInvoice, book_invoice, counters, mark_paid_many
from riso.shared import AllowAll, RequestContext
from tests.api.conftest import Fresh
from tests.factories import make_invoice

TELEKOM = "35763469"
SYSTEM = RequestContext("test", None, policy=AllowAll())


def _url(fresh: Fresh, invoice_id: str, step: str = "") -> str:
    return f"/api/customers/{fresh.boldog}/invoices/{invoice_id}{'/' + step if step else ''}"


def _check(fresh: Fresh, client, invoice_id: str, case_fields: dict) -> dict:
    response = client.post(_url(fresh, invoice_id, "check"), json=case_fields)
    assert response.status_code == 200, response.text
    return response.json()


def _book(fresh: Fresh, client, invoice: dict, action="accepted", coding=None, step="book"):
    coding = coding or _coding(invoice["proposal"])
    return client.post(_url(fresh, invoice["id"], step), json={"action": action, "coding": coding})


def _coding(proposal: dict) -> dict:
    """The proposal's coding, as a copy to edit."""
    return copy.deepcopy({k: proposal[k] for k in ("document", "posting", "budget")})


def _invoice(fresh: Fresh, client, case_id: str, **changes) -> dict:
    """A dataset case's invoice, entered unchecked and checked through the route."""
    invoice_id = make_invoice(fresh.services, fresh.boldog, case_id, check=False)
    with fresh.services.uow(immediate=False) as uow:
        fields = uow.invoices.get(fresh.boldog, invoice_id).fields
    assert fields is not None
    data = fields.model_dump(mode="json")
    for part, values in changes.items():
        data[part] = data[part] | values
    return _check(fresh, client, invoice_id, data)


def _memory(fresh: Fresh):
    return fresh.services.supplier_state().memory(fresh.boldog)


def _series(fresh: Fresh, client, code="FD") -> dict:
    items = client.get(f"/api/customers/{fresh.boldog}/number-series?year=2026").json()["items"]
    return next(s for s in items if s["series"] == code)


def test_checking_codes_the_invoice_and_records_its_basis(fresh):
    user = fresh.login("user")
    invoice = _invoice(fresh, user, "anchor-telekom")
    assert invoice["state"] == "ready" and invoice["needs_review"] is False
    assert invoice["proposal"]["invoice_id"] == invoice["id"]
    assert invoice["proposal"]["budget"][0]["key"] == "632005 41 01 110 000"
    assert invoice["basis"]["year"] == 2026 and len(invoice["basis"]["version_ids"]) >= 4
    assert invoice["basis"]["conventions_revision"] >= 1
    assert set(invoice["actions"]) == {"check", "recode", "book", "discard"}
    assert invoice["source_ref"] == "anchor-telekom" and invoice["channel"] == "dataset"


def test_accepting_a_proposal_makes_a_precedent_and_uses_up_the_number(fresh):
    user = fresh.login("user")
    invoice = _invoice(fresh, user, "anchor-telekom")
    response = _book(fresh, user, invoice)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["invoice"]["state"] == "booked" and body["invoice"]["number"] == "FD/144/26"
    assert body["placement"] == {
        "number": "FD/144/26",
        "requested": "FD/144/26",
        "moved": False,
        "shifts": [],
    }
    telekom = _memory(fresh).find(TELEKOM)
    assert telekom is not None and len(telekom.precedents) == 2  # the screenshot's and this one
    assert telekom.precedents[0].document_number == "FD/144/26"
    again = _invoice(fresh, user, "anchor-telekom")
    assert "FD/144/26 is already used" in again["proposal"]["validation"]["warnings"]


def test_a_correction_is_stored_as_the_accountant_entered_it(fresh):
    user = fresh.login("user")
    invoice = _invoice(fresh, user, "anchor-telekom")
    final = _coding(invoice["proposal"])
    final["budget"][0] |= {
        "key": "632003 41 01 110 001",
        "ek": "632003",
        "analytika": "001",
        "text": "telefon,fax",
    }
    response = _book(fresh, user, invoice, "corrected", final)
    assert response.status_code == 200, response.text
    assert response.json()["invoice"]["booking"]["action"] == "corrected"
    recoded = _invoice(fresh, user, "anchor-telekom")
    assert recoded["proposal"]["budget"][0]["key"] == "632003 41 01 110 001"  # the newest


def test_a_correction_must_use_codes_from_the_dictionaries(fresh):
    user = fresh.login("user")
    invoice = _invoice(fresh, user, "anchor-telekom")
    before = _memory(fresh)
    final = _coding(invoice["proposal"])
    final["posting"][0]["md"] = "518 999"
    response = _book(fresh, user, invoice, "corrected", final)
    assert response.status_code == 422
    assert any("518 999" in e["msg"] for e in response.json()["detail"])
    detail = user.get(_url(fresh, invoice["id"])).json()
    assert (detail["state"], detail["booking"]) == (invoice["state"], None)
    assert _memory(fresh) == before
    assert _series(fresh, user)["last_used"] == 222


def test_an_accepted_proposal_cannot_carry_changes(fresh):
    user = fresh.login("user")
    invoice = _invoice(fresh, user, "anchor-telekom")
    final = _coding(invoice["proposal"])
    final["posting"][0]["text"] = "iný text"
    response = _book(fresh, user, invoice, "accepted", final)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "action"]


def test_a_picked_position_brings_its_whole_line(fresh):
    user = fresh.login("user")
    invoice = _invoice(fresh, user, "anchor-telekom")
    line = user.post(
        _url(fresh, invoice["id"], "line"), json={"budget_key": "632003 41 09 111 000"}
    )
    assert line.status_code == 200, line.text
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
    unknown = user.post(
        _url(fresh, invoice["id"], "line"), json={"budget_key": "632003 41 09 111 999"}
    )
    assert unknown.status_code == 404


def test_alternatives_carry_the_whole_line(fresh):
    invoice = _invoice(fresh, fresh.login("user"), "anchor-telekom")
    assert invoice["proposal"]["alternatives"]
    for alternative in invoice["proposal"]["alternatives"]:
        assert alternative["md"] and alternative["dal"] and alternative["budget_text"]


def test_bookings_move_the_counter_past_the_highest_number_used(fresh):
    user = fresh.login("user")
    for case_id in ("anchor-telekom", "heldout-19-telekom-phone"):
        response = _book(fresh, user, _invoice(fresh, user, case_id))
        assert response.status_code == 200, response.text
    fd = _series(fresh, user)
    assert (fd["last_used_number"], fd["next_number"]) == ("FD/252/26", "FD/253/26")
    assert [u["number"] for u in fd["used"]] == [
        "FD/144/26",
        "FD/183/26",
        "FD/213/26",
        "FD/215/26",
        "FD/222/26",
        "FD/252/26",
    ]
    assert [u["kind"] for u in fd["used"]] == ["booked", *["external"] * 4, "booked"]


def test_a_taken_handwritten_number_goes_to_the_invoice_supplied_first(fresh):
    user = fresh.login("user")
    later = _invoice(fresh, user, "anchor-telekom", handwritten={"number": "300"})
    assert _book(fresh, user, later).json()["invoice"]["number"] == "FD/300/26"
    earlier = _invoice(
        fresh,
        user,
        "anchor-telekom",
        handwritten={"number": "300"},
        invoice={"delivery_date": "2026-06-01"},
    )
    preview = _book(fresh, user, earlier, step="booking-preview")
    assert preview.status_code == 200, preview.text
    assert preview.json() == {
        "number": "FD/300/26",
        "requested": "FD/300/26",
        "moved": False,
        "shifts": [{"invoice_id": later["id"], "old": "FD/300/26", "new": "FD/301/26"}],
    }
    booked = _book(fresh, user, earlier)
    assert booked.status_code == 200 and booked.json()["placement"] == preview.json()
    with fresh.services.uow(immediate=False) as uow:
        moved = uow.invoices.get(fresh.boldog, later["id"])
        history = uow.invoices.history(fresh.boldog, later["id"])
    assert moved.number == "FD/301/26"
    assert history[-1].kind.value == "renumbered"
    assert history[-1].details == {"from": "FD/300/26", "to": "FD/301/26", "by": earlier["id"]}
    numbers = [p.document_number for p in _memory(fresh).find(TELEKOM).precedents[:2]]
    assert numbers == ["FD/300/26", "FD/301/26"]  # the moved precedent follows its invoice
    third = _invoice(fresh, user, "anchor-telekom", handwritten={"number": "300"})
    placed = _book(fresh, user, third).json()["placement"]
    assert (placed["number"], placed["moved"]) == ("FD/302/26", True)  # supplied last


def test_a_booking_that_would_move_a_paid_number_is_refused(fresh):
    user = fresh.login("user")
    first = _invoice(fresh, user, "anchor-telekom", handwritten={"number": "300"})
    _book(fresh, user, first)
    paid = user.post(_url(fresh, first["id"], "pay"), json={"paid_on": "2026-07-01"})
    assert paid.status_code == 200 and paid.json()["state"] == "paid"
    earlier = _invoice(
        fresh,
        user,
        "anchor-telekom",
        handwritten={"number": "300"},
        invoice={"delivery_date": "2026-06-01"},
    )
    refused = _book(fresh, user, earlier)
    assert refused.status_code == 409
    assert "FD/300/26 is exported or paid" in refused.json()["detail"]
    assert (refused.json()["code"], refused.json()["number"]) == ("number_frozen", "FD/300/26")
    fd = _series(fresh, user)
    assert [u["number"] for u in fd["used"] if u["kind"] == "booked"] == ["FD/300/26"]


def test_a_number_that_does_not_fit_the_series_is_refused(fresh):
    user = fresh.login("user")
    invoice = _invoice(fresh, user, "anchor-telekom")
    final = _coding(invoice["proposal"])
    final["document"]["number"] = "FD/144/25"
    response = _book(fresh, user, invoice, "corrected", final)
    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "number_pattern"


def test_unbooking_keeps_a_number_that_is_not_the_last(fresh):
    user = fresh.login("user")
    invoice = _invoice(fresh, user, "anchor-telekom")
    _book(fresh, user, invoice)
    response = user.post(_url(fresh, invoice["id"], "unbook"), json={"reason": "zlý dodávateľ"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "ready" and body["booking"] is None and body["number"] is None
    assert len(_memory(fresh).find(TELEKOM).precedents) == 1  # the booking's precedent went
    held = {u["number"]: u for u in _series(fresh, user)["used"]}
    assert held["FD/144/26"]["kind"] == "reserved"
    assert "FD/144/26 is already used" not in body["proposal"]["validation"]["warnings"]
    again = _book(fresh, user, body)
    assert again.status_code == 200 and again.json()["invoice"]["number"] == "FD/144/26"


def test_unbooking_the_last_number_frees_it(fresh):
    user = fresh.login("user")
    invoice = _invoice(fresh, user, "heldout-19-telekom-phone")
    _book(fresh, user, invoice)
    assert user.post(_url(fresh, invoice["id"], "unbook"), json={}).status_code == 200
    fd = _series(fresh, user)
    assert fd["last_used"] == 251 and "FD/252/26" not in [u["number"] for u in fd["used"]]


def test_discarding_lets_a_kept_number_go(fresh):
    user = fresh.login("user")
    invoice = _invoice(fresh, user, "anchor-telekom")
    _book(fresh, user, invoice)
    user.post(_url(fresh, invoice["id"], "unbook"), json={})
    response = user.post(_url(fresh, invoice["id"], "discard"), json={"reason": "duplicitná"})
    assert response.status_code == 200 and response.json()["state"] == "discarded"
    assert "FD/144/26" not in [u["number"] for u in _series(fresh, user)["used"]]
    assert response.json()["actions"] == []
    assert user.post(_url(fresh, invoice["id"], "recode")).status_code == 409


def test_a_coding_without_lists_for_the_year_leaves_the_invoice_checked(fresh):
    user = fresh.login("user")
    invoice = _invoice(fresh, user, "anchor-telekom", handwritten={"date": "2031-01-05"})
    assert invoice["state"] == "checked" and invoice["proposal"] is None
    assert "2031" in invoice["coding_error"]
    assert "book" not in invoice["actions"]


def test_a_series_the_lists_do_not_have_leaves_the_invoice_checked(fresh):
    """The document series list can change after the parameters name a series; coding then
    fails with the reason, not with a server error (found in P2-M4-T10)."""
    user = fresh.login("user")
    url = f"/api/customers/{fresh.boldog}/parameters"
    values = user.get(url, params={"year": 2026}).json()["values"]
    changed = {**values, "default_series": "FX"}
    assert user.put(url, params={"year": 2026}, json={"values": changed}).status_code == 200
    invoice = _invoice(fresh, user, "anchor-telekom")
    assert invoice["state"] == "checked" and invoice["proposal"] is None
    assert "FX" in invoice["coding_error"]
    document = invoice["fields"]
    coded = user.post(f"/api/customers/{fresh.boldog}/code", json=document)
    assert coded.status_code == 409 and "FX" in coded.json()["detail"]


def test_the_engine_reads_the_numbers_from_the_database(fresh):
    user = fresh.login("user")
    _book(fresh, user, _invoice(fresh, user, "anchor-telekom"))
    with fresh.services.uow(immediate=False) as uow:
        found = counters(uow, fresh.boldog, "00305863")
    assert "FD/144/26" in found.used_numbers and found.last_used["FD/2026"] == 222


def test_a_failing_booking_changes_nothing(fresh, monkeypatch):
    """The booking renumbers an earlier booked invoice, adds a precedent and takes a number;
    the audit then fails, and all of it is rolled back."""
    user = fresh.login("user")
    first = _invoice(fresh, user, "anchor-telekom", handwritten={"number": "300"})
    _book(fresh, user, first)
    earlier = _invoice(
        fresh,
        user,
        "anchor-telekom",
        handwritten={"number": "300"},
        invoice={"delivery_date": "2026-06-01"},
    )
    memory = _memory(fresh)
    with fresh.services.uow(immediate=False) as uow:
        numbers = counters(uow, fresh.boldog, "00305863")
    record = SqlAuditRecorder.record

    def failing(self, ctx, action, **kwargs):
        if action == "invoice.booked":
            raise RuntimeError("the disk is full")
        return record(self, ctx, action, **kwargs)

    monkeypatch.setattr(SqlAuditRecorder, "record", failing)
    coding = Coding.model_validate(_coding(earlier["proposal"]))
    cmd = BookInvoice(fresh.boldog, earlier["id"], "accepted", coding)
    with pytest.raises(RuntimeError, match="disk is full"):
        book_invoice(SYSTEM, fresh.services.uow(), fresh.services.reference_data(), cmd)
    with fresh.services.uow(immediate=False) as uow:
        assert uow.invoices.get(fresh.boldog, earlier["id"]).state.value == earlier["state"]
        assert uow.invoices.get(fresh.boldog, first["id"]).number == "FD/300/26"
        assert uow.invoices.history(fresh.boldog, first["id"])[-1].kind.value == "booked"
        assert counters(uow, fresh.boldog, "00305863") == numbers
    assert _memory(fresh) == memory


def test_paying_several_reports_each_invoice(fresh):
    user = fresh.login("user")
    booked = _invoice(fresh, user, "anchor-telekom")
    _book(fresh, user, booked)
    ready = _invoice(fresh, user, "heldout-19-telekom-phone")
    results = mark_paid_many(
        SYSTEM,
        fresh.services.uow,
        fresh.boldog,
        [booked["id"], ready["id"], "no-such-invoice", booked["id"]],
        date(2026, 7, 2),
    )
    assert [(r.invoice_id, r.ok, r.code) for r in results] == [
        (booked["id"], True, None),
        (ready["id"], False, "invalid_state"),
        ("no-such-invoice", False, "not_found"),
    ]
    held = {u["number"]: u for u in _series(fresh, user)["used"]}
    assert held["FD/144/26"]["frozen"] is True
