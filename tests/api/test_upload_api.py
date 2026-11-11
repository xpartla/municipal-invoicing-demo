"""Uploads, documents and duplicates (P2-M5-T02, plan §7.3, §8.2, §10.5, decision 18): the
type comes from the content; files over 20 MB or 5 pages are refused; the same file twice
is refused with a link to its invoice; each taken file becomes an invoice waiting for its
`extract_document` job; Úložisko lists the customer's files."""

import hashlib
import io

from PIL import Image
from sqlalchemy import select

from riso.audit.infrastructure.orm import AuditEventRow
from riso.jobs.infrastructure.orm import JobRow
from riso.testdata.scans import SAMPLES_DIR
from tests.api.conftest import Fresh

JPEG_SAMPLE = SAMPLES_DIR / "heldout-07-hornbach-kd.scan.jpg"


def _image(fmt: str, frames: int = 1, colour: str = "white") -> bytes:
    out = io.BytesIO()
    pages = [Image.new("RGB", (200, 280), colour) for _ in range(frames)]
    pages[0].save(out, fmt, save_all=frames > 1, append_images=pages[1:])
    return out.getvalue()


def _pdf(pages: int = 1, colour: str = "white") -> bytes:
    return _image("PDF", pages, colour)


def _upload(client, customer_id: str, *files: tuple[str, bytes]):
    return client.post(
        f"/api/customers/{customer_id}/documents",
        files=[("files", (name, data, "application/octet-stream")) for name, data in files],
    )


def test_pdf_jpeg_png_and_tiff_are_taken_and_each_becomes_an_invoice_with_its_job(fresh: Fresh):
    user = fresh.login("user")
    files = [
        ("faktura.pdf", _pdf(2)),
        ("sken.jpg", JPEG_SAMPLE.read_bytes()),
        ("foto.png", _image("PNG")),
        ("sken.tif", _image("TIFF", 3)),
    ]
    response = _upload(user, fresh.boldog, *files)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["accepted"] == 4 and body["rejected"] == 0
    for item, (name, data) in zip(body["items"], files, strict=True):
        assert item["status"] == "accepted" and item["filename"] == name
        document = user.get(f"/api/customers/{fresh.boldog}/documents/{item['document_id']}")
        assert document.status_code == 200
        assert document.json()["invoice_id"] == item["invoice_id"]
        invoice = user.get(f"/api/customers/{fresh.boldog}/invoices/{item['invoice_id']}")
        assert invoice.status_code == 200, invoice.text
        assert invoice.json()["state"] == "extracting" and invoice.json()["channel"] == "scan"
        stored = user.get(f"/api/customers/{fresh.boldog}/documents/{item['document_id']}/file")
        assert stored.content == data
        assert stored.headers["content-security-policy"] == "sandbox"
        assert stored.headers["content-disposition"].startswith("attachment;")
        job = user.get(f"/api/customers/{fresh.boldog}/jobs/{item['job_id']}")
        assert job.status_code == 200 and job.json()["kind"] == "extract_document"
    pages = [
        user.get(f"/api/customers/{fresh.boldog}/documents/{i['document_id']}").json()
        for i in body["items"]
    ]
    assert [(p["media_type"], p["pages"]) for p in pages] == [
        ("application/pdf", 2),
        ("image/jpeg", 1),
        ("image/png", 1),
        ("image/tiff", 3),
    ]


def test_the_type_comes_from_the_content_not_the_name(fresh: Fresh):
    user = fresh.login("user")
    response = _upload(
        user,
        fresh.boldog,
        ("faktura.pdf", b"just some text, not a PDF"),
        ("faktura.xml", b"PK\x03\x04 a spreadsheet named as XML"),
        ("prazdny.pdf", b""),
        ("obrazok.txt", _image("PNG")),
    )
    items = response.json()["items"]
    assert [(i["status"], i["reason"]) for i in items] == [
        ("rejected", "file_type"),
        ("rejected", "file_type"),
        ("rejected", "file_empty"),
        ("accepted", None),
    ]
    assert items[0]["document_id"] is None and items[0]["invoice_id"] is None


def test_too_large_and_too_many_pages_are_refused(fresh: Fresh):
    user = fresh.login("user")
    big = b"%PDF-1.4\n" + b"0" * (20 * 1024 * 1024)
    response = _upload(user, fresh.boldog, ("velky.pdf", big), ("dlhy.pdf", _pdf(6)))
    assert [(i["status"], i["reason"]) for i in response.json()["items"]] == [
        ("rejected", "file_too_large"),
        ("rejected", "too_many_pages"),
    ]
    assert "6 pages" in response.json()["items"][1]["message"]
    assert _upload(user, fresh.boldog, ("piat.pdf", _pdf(5))).json()["accepted"] == 1


def test_a_damaged_pdf_is_taken_for_its_extraction_to_say_what_is_wrong(fresh: Fresh):
    user = fresh.login("user")
    item = _upload(user, fresh.boldog, ("poskodeny.pdf", b"%PDF-1.4\n garbage")).json()["items"][0]
    assert item["status"] == "accepted"
    document = user.get(f"/api/customers/{fresh.boldog}/documents/{item['document_id']}").json()
    assert document["pages"] is None


def test_the_same_file_again_is_refused_with_a_link_to_its_invoice(fresh: Fresh):
    user = fresh.login("user")
    data = _pdf(1, "ivory")
    first = _upload(user, fresh.boldog, ("a.pdf", data)).json()["items"][0]
    again = _upload(user, fresh.boldog, ("b.pdf", data), ("c.pdf", data)).json()["items"]
    for item in again:
        assert item["status"] == "rejected" and item["reason"] == "duplicate"
        assert item["duplicate_of"] == first["invoice_id"]
        assert item["document_id"] == first["document_id"]
        assert item["invoice_id"] is None
    # Within one request too: the second copy is a duplicate of the first.
    pair = _upload(user, fresh.boldog, ("d.pdf", _pdf(1, "beige")), ("e.pdf", _pdf(1, "beige")))
    first_of_pair, second_of_pair = pair.json()["items"]
    assert first_of_pair["status"] == "accepted"
    assert second_of_pair["duplicate_of"] == first_of_pair["invoice_id"]
    with fresh.services.uow(immediate=False) as uow:
        jobs = uow.session.scalars(select(JobRow).where(JobRow.kind == "extract_document")).all()
    assert len(jobs) == 2


def test_another_customer_may_hold_the_same_file_but_not_see_this_one(fresh: Fresh):
    staff = fresh.login("staff")
    other = fresh.done.customers["Obec Vzorová Lehota"]
    data = _pdf(1, "linen")
    mine = _upload(staff, fresh.boldog, ("a.pdf", data)).json()["items"][0]
    theirs = _upload(staff, other, ("a.pdf", data)).json()["items"][0]
    assert mine["status"] == theirs["status"] == "accepted"
    assert mine["document_id"] != theirs["document_id"]
    foreign = staff.get(f"/api/customers/{other}/documents/{mine['document_id']}")
    assert foreign.status_code == 404
    assert (
        staff.get(f"/api/customers/{other}/documents/{mine['document_id']}/file").status_code == 404
    )


def test_a_reader_may_look_but_not_upload(fresh: Fresh):
    user, viewer = fresh.login("user"), fresh.login("viewer")
    item = _upload(user, fresh.boldog, ("a.png", _image("PNG", colour="gray"))).json()["items"][0]
    assert _upload(viewer, fresh.boldog, ("b.png", _image("PNG"))).status_code == 403
    assert (
        viewer.get(f"/api/customers/{fresh.boldog}/documents/{item['document_id']}").status_code
        == 200
    )


def test_an_upload_is_audited_with_ids_and_no_file_name(fresh: Fresh):
    user = fresh.login("user")
    item = _upload(user, fresh.boldog, ("Ján Novák faktúra.pdf", _pdf())).json()["items"][0]
    with fresh.services.uow(immediate=False) as uow:
        rows = uow.session.scalars(
            select(AuditEventRow).where(
                AuditEventRow.action.in_(["document.uploaded", "invoice.uploaded"])
            )
        ).all()
        assert {r.action for r in rows} == {"document.uploaded", "invoice.uploaded"}
        assert {r.target_id for r in rows} == {item["document_id"], item["invoice_id"]}
        assert all("Novák" not in str(r.details) for r in rows)


def test_more_than_twenty_files_or_none_are_refused(fresh: Fresh):
    user = fresh.login("user")
    many = [(f"{i}.png", _image("PNG")) for i in range(21)]
    assert _upload(user, fresh.boldog, *many).status_code == 422
    assert user.post(f"/api/customers/{fresh.boldog}/documents").status_code == 422


def test_the_extraction_job_runs_and_its_invoice_waits_for_manual_entry(fresh: Fresh):
    """Here the OCR models are missing (a fresh var directory), so the reading fails with
    its reason (`no_models`); the job itself succeeds."""
    user = fresh.login("user")
    item = _upload(user, fresh.boldog, ("a.png", _image("PNG", colour="tan"))).json()["items"][0]
    fresh.services.worker().run_pending()
    invoice = user.get(f"/api/customers/{fresh.boldog}/invoices/{item['invoice_id']}").json()
    assert invoice["state"] == "extraction_failed"
    job = user.get(f"/api/customers/{fresh.boldog}/jobs/{item['job_id']}").json()
    assert job["status"] == "succeeded"


def test_storage_lists_the_files_with_what_uses_them(fresh: Fresh):
    user = fresh.login("user")
    pdf, png = _pdf(1, "khaki"), _image("PNG", colour="navy")
    items = _upload(user, fresh.boldog, ("a.pdf", pdf), ("b.png", png)).json()["items"]
    listing = user.get(f"/api/customers/{fresh.boldog}/files").json()
    documents = [f for f in listing["items"] if f["kind"] == "document"]
    assert {(f["id"], f["invoice_id"]) for f in documents} == {
        (i["document_id"], i["invoice_id"]) for i in items
    }
    assert listing["kinds"]["document"] == {"count": 2, "size": len(pdf) + len(png)}
    assert listing["size"] == sum(k["size"] for k in listing["kinds"].values())
    assert listing["kinds"]["import"]["count"] == 0  # Boldog's lists were seeded, not imported
    only = user.get(f"/api/customers/{fresh.boldog}/files", params={"kind": "document", "size": 1})
    assert only.json()["total"] == 2 and len(only.json()["items"]) == 1
    assert hashlib.sha256(pdf).hexdigest() != hashlib.sha256(png).hexdigest()
    viewer = fresh.login("viewer")
    assert viewer.get(f"/api/customers/{fresh.boldog}/files").status_code == 200
