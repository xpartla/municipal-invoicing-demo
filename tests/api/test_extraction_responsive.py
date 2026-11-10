"""The API stays responsive while a page is read (P2-M5-T03, plan §4.6): extraction runs in
the worker's thread (and Tesseract in its own process), never in a request."""

import io
import threading
import time

from PIL import Image

from riso.api import Settings, create_app
from riso.intake.application import PageImage
from riso.intake.domain.layout import PageLayout
from tests.api.conftest import ApiClient, Fresh
from tests.conftest import SEED_PASSWORD


class BlockingReader:
    """Reads a page only when the test lets it."""

    engine = "blocking"
    version = "1"

    def __init__(self) -> None:
        self.reading = threading.Event()
        self.release = threading.Event()

    def read(self, page: PageImage) -> PageLayout:
        self.reading.set()
        assert self.release.wait(20), "the test never released the reader"
        return PageLayout(page.index, page.image.width, page.image.height, page.dpi, ())


def _png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (300, 400), "white").save(out, "PNG")
    return out.getvalue()


def _invoice(client: ApiClient, customer_id: str, invoice_id: str) -> dict:
    return client.get(f"/api/customers/{customer_id}/invoices/{invoice_id}").json()


def test_requests_are_answered_while_a_page_is_being_read(fresh: Fresh):
    reader = BlockingReader()
    fresh.services.document_reader = reader
    settings = Settings(
        var_dir=fresh.services.settings.var_dir, platform=fresh.services.settings, run_worker=True
    )
    app = create_app(settings, services=fresh.services)
    with ApiClient(app) as client:
        client.login(fresh.done.users["user"][1], SEED_PASSWORD)
        upload = client.post(
            f"/api/customers/{fresh.boldog}/documents",
            files=[("files", ("sken.png", _png(), "image/png"))],
        )
        item = upload.json()["items"][0]
        assert reader.reading.wait(15), "the worker never started reading"

        started = time.perf_counter()
        me = client.get("/api/me")
        invoice = _invoice(client, fresh.boldog, item["invoice_id"])
        elapsed = time.perf_counter() - started
        assert me.status_code == 200 and invoice["state"] == "extracting"
        assert elapsed < 1.0, f"the API took {elapsed:.2f} s while a page was read"

        reader.release.set()
        deadline = time.monotonic() + 15
        while _invoice(client, fresh.boldog, item["invoice_id"])["state"] == "extracting":
            assert time.monotonic() < deadline, "the extraction never ended"
            time.sleep(0.2)
        assert _invoice(client, fresh.boldog, item["invoice_id"])["state"] == "extraction_failed"
