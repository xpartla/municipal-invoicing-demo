"""E-invoices in the intake flow (P2-M6-T05, plan §8.4, decision 65): an uploaded UBL or
ISDOC file, or a PDF carrying one, becomes an extracted invoice without OCR. The booking
date is suggested as the upload date and the number left to the booking (decision 61), both
for the user to confirm; the rendered view and the raw XML are served for the viewer."""

import datetime as dt
import re

from riso.intake.application import PageImage
from riso.intake.domain.layout import Box, PageLayout
from riso.shared.clock import local_date
from riso.testdata.einvoices import SAMPLES_DIR, attach, ubl_invoice
from riso.testdata.scans import dataset_cases
from tests.api.conftest import Fresh

HORNBACH = "heldout-07-hornbach-kd"


class NoOcr:
    engine = "none"
    version = "0"

    def read(self, page: PageImage) -> PageLayout:
        raise AssertionError("an e-invoice was sent to OCR")

    def read_digits(self, page: PageImage, region: Box) -> PageLayout:
        raise AssertionError("an e-invoice was sent to OCR")


def _upload(fresh: Fresh, user, name: str, data: bytes) -> dict:
    response = user.post(
        f"/api/customers/{fresh.boldog}/documents",
        files=[("files", (name, data, "application/octet-stream"))],
    )
    assert response.status_code == 200, response.text
    return response.json()["items"][0]


def _invoice(fresh: Fresh, user, invoice_id: str) -> dict:
    return user.get(f"/api/customers/{fresh.boldog}/invoices/{invoice_id}").json()


def _base(fresh: Fresh, item: dict) -> str:
    return f"/api/customers/{fresh.boldog}/documents/{item['document_id']}"


def test_a_ubl_upload_becomes_an_extracted_invoice_with_the_defaults(fresh: Fresh):
    fresh.services.document_reader = NoOcr()
    user = fresh.login("user")
    item = _upload(fresh, user, "faktura.xml", (SAMPLES_DIR / f"{HORNBACH}.ubl.xml").read_bytes())
    assert item["status"] == "accepted"
    document = user.get(_base(fresh, item)).json()
    assert document["media_type"] == "application/xml" and document["pages"] is None
    fresh.services.worker().run_pending()

    invoice = _invoice(fresh, user, item["invoice_id"])
    assert invoice["state"] == "extracted" and invoice["channel"] == "einvoice"
    fields = invoice["fields"]
    assert fields["intake"] == {"channel": "einvoice", "format": "ubl"}
    assert fields["supplier"]["ico"] == "35838949"
    assert fields["invoice"]["number"] == "2026-418-019944"
    assert fields["totals"]["gross"] == 403.42
    # Never filled on their own (decision 65): the user confirms the booking date, and the
    # number is the booking's (decision 61).
    assert fields["handwritten"] == {"date": None, "number": None}

    extraction = user.get(f"{_base(fresh, item)}/extraction").json()
    assert (extraction["engine"], extraction["engine_version"], extraction["source"]) == (
        "ubl",
        "2.1",
        "einvoice",
    )
    assert extraction["pages"] == 0 and extraction["evidence"] == {}
    assert set(extraction["confidence"].values()) == {1.0}
    assert extraction["warnings"] == []
    note = extraction["note"]
    uploaded = local_date(dt.datetime.fromisoformat(document["uploaded_at"]))
    assert note["date"] == [
        {"value": uploaded.isoformat(), "source": "upload", "plausible": True, "reasons": []}
    ]
    assert note["number"] == [] and extraction["note_image"] is False
    assert isinstance(extraction["number_preview"], int) and extraction["number_preview"] >= 1
    assert user.get(f"{_base(fresh, item)}/note").status_code == 404


def test_the_confirmed_e_invoice_is_coded_and_booked_by_its_date_of_supply(fresh: Fresh):
    user = fresh.login("user")
    item = _upload(fresh, user, "faktura.xml", (SAMPLES_DIR / f"{HORNBACH}.ubl.xml").read_bytes())
    fresh.services.worker().run_pending()
    invoice = _invoice(fresh, user, item["invoice_id"])
    extraction = user.get(f"{_base(fresh, item)}/extraction").json()
    fields = invoice["fields"]
    fields["handwritten"]["date"] = extraction["note"]["date"][0]["value"]
    checked = user.post(
        f"/api/customers/{fresh.boldog}/invoices/{item['invoice_id']}/check", json=fields
    )
    assert checked.status_code == 200, checked.text
    proposal = checked.json()["proposal"]
    assert proposal["document"]["booking_date"] == fields["handwritten"]["date"]
    number = re.fullmatch(r"FD/(\d+)/26", proposal["document"]["number"])
    assert number is not None and int(number.group(1)) == extraction["number_preview"]

    coding = {k: proposal[k] for k in ("document", "posting", "budget")}
    booked = user.post(
        f"/api/customers/{fresh.boldog}/invoices/{item['invoice_id']}/book",
        json={"action": "accepted", "coding": coding},
    )
    assert booked.status_code == 200, booked.text
    placement = booked.json()["placement"]
    # No number was asked for: the booking placed the invoice by its date of supply.
    assert placement["requested"] is None and placement["moved"] is False
    assert booked.json()["invoice"]["state"] == "booked"
    assert re.fullmatch(r"FD/\d+/26", placement["number"])


def test_an_isdoc_pdf_is_read_from_its_attachment_with_its_pages(fresh: Fresh):
    fresh.services.document_reader = NoOcr()
    user = fresh.login("user")
    data = (SAMPLES_DIR / f"{HORNBACH}.isdoc.pdf").read_bytes()
    item = _upload(fresh, user, "faktura.pdf", data)
    fresh.services.worker().run_pending()
    invoice = _invoice(fresh, user, item["invoice_id"])
    assert invoice["state"] == "extracted" and invoice["channel"] == "einvoice"
    assert invoice["fields"]["intake"] == {"channel": "einvoice", "format": "isdoc_pdf"}
    assert invoice["fields"]["lines"][0]["gross"] is not None  # ISDOC carries line gross
    extraction = user.get(f"{_base(fresh, item)}/extraction").json()
    assert (extraction["engine"], extraction["source"], extraction["pages"]) == (
        "isdoc",
        "einvoice",
        1,
    )
    page = user.get(f"{_base(fresh, item)}/pages/0")
    assert page.status_code == 200 and page.headers["content-type"] == "image/jpeg"


def test_the_rendered_view_and_the_raw_xml_are_served(fresh: Fresh):
    user, viewer = fresh.login("user"), fresh.login("viewer")
    data = (SAMPLES_DIR / f"{HORNBACH}.isdoc.pdf").read_bytes()
    item = _upload(fresh, user, "faktura.pdf", data)
    fresh.services.worker().run_pending()
    view = viewer.get(f"{_base(fresh, item)}/einvoice")
    assert view.status_code == 200, view.text
    body = view.json()
    assert (body["format"], body["family"], body["version"]) == ("isdoc", "isdoc", "6.0.2")
    assert body["attachment"] == "2026-418-019944.isdoc"
    assert body["failure"] is None and body["schema_errors"] == []
    assert body["document"]["supplier"]["name"].startswith("HORNBACH")
    assert body["taxes"][0]["rate"] == 23 and body["payable"] == 403.42
    assert body["xml"].startswith("<?xml") and "<ID>2026-418-019944</ID>" in body["xml"]
    assert body["truncated"] is False


def test_an_xml_that_is_not_an_e_invoice_fails_and_still_shows_its_text(fresh: Fresh):
    user = fresh.login("user")
    item = _upload(fresh, user, "data.xml", b'<?xml version="1.0"?><orders><o id="1"/></orders>')
    fresh.services.worker().run_pending()
    invoice = _invoice(fresh, user, item["invoice_id"])
    assert invoice["state"] == "extraction_failed"
    assert invoice["extraction_error"] == "einvoice_unknown"
    body = user.get(f"{_base(fresh, item)}/einvoice").json()
    assert body["failure"] == "einvoice_unknown" and body["document"] is None
    assert "<orders>" in body["xml"]


def test_an_xml_with_a_doctype_fails_unparsed(fresh: Fresh):
    user = fresh.login("user")
    xxe = b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]><r>&x;</r>'
    item = _upload(fresh, user, "zla.xml", xxe)
    fresh.services.worker().run_pending()
    assert _invoice(fresh, user, item["invoice_id"])["extraction_error"] == "xml_dtd"
    body = user.get(f"{_base(fresh, item)}/einvoice").json()
    assert body["failure"] == "xml_dtd" and "root:" not in body["xml"]


def test_a_failed_e_invoice_is_entered_by_hand(fresh: Fresh):
    case = next(c for c in dataset_cases() if c.id == HORNBACH)
    user = fresh.login("user")
    no_total = ubl_invoice(case.invoice).replace(b"TaxInclusiveAmount", b"TaxInclusiveAmountX")
    no_total = re.sub(rb"<cbc:PayableAmount[^<]*</cbc:PayableAmount>", b"", no_total)
    item = _upload(fresh, user, "faktura.xml", no_total)
    fresh.services.worker().run_pending()
    assert _invoice(fresh, user, item["invoice_id"])["extraction_error"] == "einvoice_no_total"
    entered = user.post(
        f"/api/customers/{fresh.boldog}/invoices/{item['invoice_id']}/manual",
        json=case.invoice.model_dump(mode="json"),
    )
    assert entered.status_code == 200, entered.text


def test_a_pdf_with_more_pages_than_the_cap_is_taken_when_it_carries_an_e_invoice(fresh: Fresh):
    import io

    import pypdfium2

    case = next(c for c in dataset_cases() if c.id == HORNBACH)
    pdf = pypdfium2.PdfDocument.new()
    for _ in range(7):
        pdf.new_page(595, 842)
    out = io.BytesIO()
    pdf.save(out)
    long_pdf = out.getvalue()
    user = fresh.login("user")
    refused = _upload(fresh, user, "dlhe.pdf", long_pdf)
    assert (refused["status"], refused["reason"]) == ("rejected", "too_many_pages")
    item = _upload(
        fresh, user, "dlhe-s-ubl.pdf", attach(long_pdf, "f.xml", ubl_invoice(case.invoice))
    )
    assert item["status"] == "accepted"
    fresh.services.worker().run_pending()
    extraction = user.get(f"{_base(fresh, item)}/extraction").json()
    assert extraction["source"] == "einvoice" and extraction["pages"] == 5
