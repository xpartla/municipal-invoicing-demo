"""The extraction job end to end (P2-M5-T07, plan §4.7, §7.1, §8.2): an upload becomes an
extracted invoice waiting for the check step, with the reading kept for it; a file that
cannot be read fails with its reason, and is retried or entered by hand."""

import io

from PIL import Image

from riso.dataset import load_cases
from riso.intake.application import EXTRACT_JOB, PageImage
from riso.intake.domain.layout import Box, PageLayout
from riso.intake.infrastructure.recorded import RecordedReader
from riso.jobs import JobContext
from riso.testdata.scans import SAMPLES_DIR
from tests.api.conftest import Fresh

SCAN = "heldout-07-hornbach-kd.scan.jpg"
TELEKOM = next(c for c in load_cases() if c.id == "anchor-telekom")


def _upload(fresh: Fresh, user, name: str, data: bytes) -> dict:
    response = user.post(
        f"/api/customers/{fresh.boldog}/documents",
        files=[("files", (name, data, "application/octet-stream"))],
    )
    assert response.status_code == 200, response.text
    return response.json()["items"][0]


def _invoice(fresh: Fresh, user, invoice_id: str) -> dict:
    return user.get(f"/api/customers/{fresh.boldog}/invoices/{invoice_id}").json()


def test_an_uploaded_scan_becomes_an_extracted_invoice_with_its_reading(fresh: Fresh):
    fresh.services.document_reader = RecordedReader()
    user = fresh.login("user")
    item = _upload(fresh, user, "sken.jpg", (SAMPLES_DIR / SCAN).read_bytes())
    fresh.services.worker().run_pending()

    invoice = _invoice(fresh, user, item["invoice_id"])
    assert invoice["state"] == "extracted" and invoice["channel"] == "scan"
    fields = invoice["fields"]
    assert fields["id"] == item["invoice_id"]
    assert fields["supplier"]["ico"] == "35838949"
    assert fields["totals"]["gross"] == 403.42
    assert fields["intake"] == {"channel": "scan", "format": "jpeg"}
    # Never accepted on their own: the user confirms the handwritten date and number.
    assert fields["handwritten"] == {"date": None, "number": None}

    base = f"/api/customers/{fresh.boldog}/documents/{item['document_id']}"
    extraction = user.get(f"{base}/extraction").json()
    assert extraction["engine"] == "recorded" and extraction["source"] == "ocr"
    assert extraction["invoice_id"] == item["invoice_id"] and extraction["pages"] == 1
    assert extraction["confidence"]["supplier.ico"] >= 0.9
    assert extraction["evidence"]["supplier.ico"]["page"] == 0
    note = extraction["note"]
    assert note["found"] and note["page"] == 0 and len(note["box"]) == 4
    assert any(s["source"] == "counter" for s in note["number"])
    page = user.get(f"{base}/pages/0")
    assert page.headers["content-type"] == "image/jpeg"
    image = Image.open(io.BytesIO(page.content))
    left, top, right, bottom = extraction["evidence"]["supplier.ico"]["box"]
    assert 0 <= left < right <= image.width and 0 <= top < bottom <= image.height
    crop = user.get(f"{base}/note")
    assert crop.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(crop.content)).size == (
        note["box"][2] - note["box"][0],
        note["box"][3] - note["box"][1],
    )
    assert user.get(f"{base}/pages/1").status_code == 404
    job = user.get(f"/api/customers/{fresh.boldog}/jobs/{item['job_id']}").json()
    assert job["result"]["outcome"] == "extracted"


def test_the_extracted_invoice_is_checked_with_the_handwritten_fields_and_coded(fresh: Fresh):
    fresh.services.document_reader = RecordedReader()
    user = fresh.login("user")
    item = _upload(fresh, user, "sken.jpg", (SAMPLES_DIR / SCAN).read_bytes())
    fresh.services.worker().run_pending()
    fields = _invoice(fresh, user, item["invoice_id"])["fields"]
    fields["handwritten"] = {"date": "2026-08-27", "number": "233"}
    checked = user.post(
        f"/api/customers/{fresh.boldog}/invoices/{item['invoice_id']}/check", json=fields
    )
    assert checked.status_code == 200, checked.text
    assert checked.json()["state"] in ("ready", "needs_review")
    assert checked.json()["proposal"]["document"]["number"] == "FD/233/26"


class NoOcr:
    engine = "none"
    version = "0"

    def read(self, page: PageImage) -> PageLayout:
        raise AssertionError("a digital PDF was sent to OCR")

    def read_digits(self, page: PageImage, region: Box) -> PageLayout:
        raise AssertionError("a digital PDF was sent to OCR")


def test_a_digital_pdf_is_extracted_from_its_text_layer(fresh: Fresh):
    fresh.services.document_reader = NoOcr()
    user = fresh.login("user")
    data = (SAMPLES_DIR / "heldout-07-hornbach-kd.digital.pdf").read_bytes()
    item = _upload(fresh, user, "faktura.pdf", data)
    fresh.services.worker().run_pending()
    invoice = _invoice(fresh, user, item["invoice_id"])
    assert invoice["state"] == "extracted" and invoice["channel"] == "digital_pdf"
    assert invoice["fields"]["invoice"]["number"] == "2026-418-019944"
    assert invoice["fields"]["intake"] == {"channel": "digital_pdf", "format": "pdf"}
    base = f"/api/customers/{fresh.boldog}/documents/{item['document_id']}"
    extraction = user.get(f"{base}/extraction").json()
    assert extraction["source"] == "text_layer" and extraction["note"] is None
    assert extraction["confidence"]["invoice.number"] >= 0.9
    assert user.get(f"{base}/note").status_code == 404


def test_a_corrupt_file_fails_with_its_reason_and_is_entered_by_hand(fresh: Fresh):
    user = fresh.login("user")
    item = _upload(fresh, user, "poskodeny.pdf", b"%PDF-1.4\n not really a pdf")
    fresh.services.worker().run_pending()
    invoice = _invoice(fresh, user, item["invoice_id"])
    assert invoice["state"] == "extraction_failed" and invoice["extraction_error"] == "unreadable"
    base = f"/api/customers/{fresh.boldog}/documents/{item['document_id']}"
    assert user.get(f"{base}/extraction").status_code == 404

    retried = user.post(f"/api/customers/{fresh.boldog}/invoices/{item['invoice_id']}/extraction")
    assert retried.status_code == 202, retried.text
    assert _invoice(fresh, user, item["invoice_id"])["state"] == "extracting"
    fresh.services.worker().run_pending()
    assert _invoice(fresh, user, item["invoice_id"])["extraction_error"] == "unreadable"

    fields = TELEKOM.invoice.model_dump(mode="json")
    entered = user.post(
        f"/api/customers/{fresh.boldog}/invoices/{item['invoice_id']}/manual", json=fields
    )
    assert entered.status_code == 200, entered.text
    body = entered.json()
    assert body["state"] in ("ready", "needs_review") and body["channel"] == "scan"
    assert body["document_id"] == item["document_id"]
    assert body["fields"]["intake"]["channel"] == "manual"
    again = user.post(f"/api/customers/{fresh.boldog}/invoices/{item['invoice_id']}/extraction")
    assert again.status_code == 409  # only a failed extraction is retried


def test_a_page_without_a_recording_fails_with_its_reason(fresh: Fresh):
    fresh.services.document_reader = RecordedReader()
    user = fresh.login("user")
    out = io.BytesIO()
    Image.new("RGB", (400, 560), "white").save(out, "PNG")
    item = _upload(fresh, user, "nova.png", out.getvalue())
    fresh.services.worker().run_pending()
    assert _invoice(fresh, user, item["invoice_id"])["extraction_error"] == "no_recording"


class Broken:
    engine = "broken"
    version = "0"

    def read(self, page: PageImage) -> PageLayout:
        raise RuntimeError("something unexpected")

    def read_digits(self, page: PageImage, region: Box) -> PageLayout:
        raise RuntimeError("something unexpected")


def test_an_unexpected_error_is_retried_and_its_last_attempt_fails_the_extraction(fresh: Fresh):
    fresh.services.document_reader = Broken()
    user = fresh.login("user")
    item = _upload(fresh, user, "sken.jpg", (SAMPLES_DIR / SCAN).read_bytes())
    jobs = fresh.services.extraction_jobs()
    payload = jobs_payload(fresh, item)
    context = fresh.services.job_context  # who started the job
    with fresh.services.jobs_uow(immediate=False) as uow:
        job = uow.jobs.get(item["job_id"])
    request = context(job)
    first = JobContext(item["job_id"], EXTRACT_JOB, 1, fresh.boldog, job.created_by, request)
    try:
        jobs.run(payload, first)
        raised = False
    except RuntimeError:
        raised = True
    assert raised and _invoice(fresh, user, item["invoice_id"])["state"] == "extracting"
    last = JobContext(item["job_id"], EXTRACT_JOB, 3, fresh.boldog, job.created_by, request)
    assert jobs.run(payload, last) == {"outcome": "extraction_failed", "reason": "extraction_error"}
    assert _invoice(fresh, user, item["invoice_id"])["extraction_error"] == "extraction_error"


def jobs_payload(fresh: Fresh, item: dict):
    from riso.intake.application import ExtractDocument

    return ExtractDocument(
        customer_id=fresh.boldog, document_id=item["document_id"], invoice_id=item["invoice_id"]
    )


def test_a_reader_sees_the_reading_but_may_not_retry(fresh: Fresh):
    fresh.services.document_reader = RecordedReader()
    user, viewer = fresh.login("user"), fresh.login("viewer")
    item = _upload(fresh, user, "sken.jpg", (SAMPLES_DIR / SCAN).read_bytes())
    fresh.services.worker().run_pending()
    base = f"/api/customers/{fresh.boldog}/documents/{item['document_id']}"
    assert viewer.get(f"{base}/extraction").status_code == 200
    assert viewer.get(f"{base}/pages/0").status_code == 200
    retry = viewer.post(f"/api/customers/{fresh.boldog}/invoices/{item['invoice_id']}/extraction")
    assert retry.status_code == 403
