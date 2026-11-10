"""A digital PDF is read from its text layer, without OCR (P2-M5-T04)."""

from riso.intake.application import PageImage
from riso.intake.domain.layout import PageLayout
from riso.testdata.scans import SAMPLES_DIR
from tests.api.conftest import Fresh


class NoOcr:
    engine = "none"
    version = "0"

    def __init__(self) -> None:
        self.pages: list[int] = []

    def read(self, page: PageImage) -> PageLayout:
        self.pages.append(page.index)
        raise AssertionError("a digital PDF was sent to OCR")


def test_a_digital_pdf_is_read_without_ocr(fresh: Fresh):
    reader = NoOcr()
    fresh.services.document_reader = reader
    user = fresh.login("user")
    digital = (SAMPLES_DIR / "heldout-07-hornbach-kd.digital.pdf").read_bytes()
    item = user.post(
        f"/api/customers/{fresh.boldog}/documents",
        files=[("files", ("faktura.pdf", digital, "application/pdf"))],
    ).json()["items"][0]
    fresh.services.worker().run_pending()
    job = user.get(f"/api/customers/{fresh.boldog}/jobs/{item['job_id']}").json()
    assert job["status"] == "succeeded" and job["result"]["reason"] == "not_extracted"
    assert reader.pages == []
