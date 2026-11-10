"""The `extract_document` job (plan §4.6, §4.7, §8.2): it reads an uploaded document and
moves its invoice to `extracted`, or to `extraction_failed` with the reason. Idempotent: an
invoice that no longer waits for the job is left alone, before anything is read.

The job runs in the worker's thread and the OCR in its own process (`TesseractReader`), so
reading a page never holds a request. A PDF with a usable text layer is read from it, without
OCR (plan §8.2, "Digital PDFs"); its note is read only when the page is a scan under the text
layer (a scanner's searchable PDF). The fields come
from the field extractor, the supplier's name from supplier memory where it was missed, and
the handwritten note's suggestions from its digits pass; the handwritten date and number stay
empty for the user to confirm. The extraction keeps the engine, the layout, the page images,
the note's crop and the time taken, and is stored with the invoice's move in one transaction.

A reading that fails says why (`unreadable`, `too_many_pages`, `too_many_pixels`,
`no_models`, `ocr_timeout`, …); anything else is retried, and the last attempt ends the
extraction with `extraction_error`.
"""

import io
import json
import time
from collections.abc import Callable
from typing import Any, Protocol

from PIL import Image
from pydantic import BaseModel, ConfigDict

from riso.identity import Permission
from riso.intake.application.enrich import SupplierNames, enrich
from riso.intake.application.note import note_readings, suggest
from riso.intake.application.ports import (
    DocumentReader,
    NoteLocator,
    PageImage,
    PagePreparer,
    TextLayer,
)
from riso.intake.application.uow import IntakeUnitOfWork
from riso.intake.domain import MediaType
from riso.intake.domain.extract import Context, FieldExtractor
from riso.intake.domain.extraction import Extraction, Source
from riso.intake.domain.layout import DocumentLayout, PageLayout, ReadingFailed
from riso.intake.domain.note import NoteSuggestions
from riso.invoicing import (
    awaits_extraction,
    complete_extraction,
    counter_hint,
    fail_extraction,
    failed_extraction_document,
    restart_extraction,
)
from riso.jobs import JobContext, JobRegistry
from riso.shared.clock import local_date
from riso.shared.context import RequestContext
from riso.shared.errors import InvalidState
from riso.shared.ports import FileStorage

EXTRACT_JOB = "extract_document"
ATTEMPTS = 3


class ExtractDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: str
    document_id: str
    invoice_id: str


class Customers(Protocol):
    def identity_of(self, customer_id: str) -> tuple[str, str]:
        """The customer's IČO and name."""
        ...


def _jpeg(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.convert("L").save(out, "JPEG", quality=85)
    return out.getvalue()


def _png(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.convert("L").save(out, "PNG")
    return out.getvalue()


_FORMATS = {
    MediaType.PDF: "pdf",
    MediaType.JPEG: "jpeg",
    MediaType.PNG: "png",
    MediaType.TIFF: "tiff",
}


class ExtractionJobs:
    def __init__(
        self,
        uow_factory: Callable[[], IntakeUnitOfWork],
        storage: FileStorage,
        reader: Callable[[], DocumentReader],
        pages: PagePreparer,
        text: TextLayer,
        locator: NoteLocator,
        customers: Customers,
        suppliers: SupplierNames,
    ) -> None:
        self._uow = uow_factory
        self._storage = storage
        self._reader = reader
        self._pages = pages
        self._text = text
        self._locator = locator
        self._customers = customers
        self._suppliers = suppliers
        self._extractor = FieldExtractor()

    def register(self, registry: JobRegistry) -> None:
        registry.register(EXTRACT_JOB, ExtractDocument, self.run, max_attempts=ATTEMPTS)

    def run(self, payload: ExtractDocument, job: JobContext) -> dict[str, Any] | None:
        with self._uow() as uow:
            if not awaits_extraction(uow, payload.customer_id, payload.invoice_id, job.job_id):
                return {"outcome": "skipped"}
            document = uow.documents.get(payload.customer_id, payload.document_id)
        with self._storage.open(document.storage_key) as handle:
            data = handle.read()
        try:
            return self._extract(payload, job, document.media_type, document.sha256, data)
        except ReadingFailed as failed:
            return self._fail(payload, job, failed.reason)
        except Exception:
            if job.attempt >= ATTEMPTS:
                return self._fail(payload, job, "extraction_error")
            raise

    def _fail(self, payload: ExtractDocument, job: JobContext, reason: str) -> dict[str, Any]:
        with self._uow() as uow:
            fail_extraction(
                job.request, uow, payload.customer_id, payload.invoice_id, job.job_id, reason
            )
            uow.commit()
        return {"outcome": "extraction_failed", "reason": reason}

    def _extract(
        self,
        payload: ExtractDocument,
        job: JobContext,
        media_type: MediaType,
        sha256: str,
        data: bytes,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        text = self._text.read(data) if media_type is MediaType.PDF else None
        source: Source = "text_layer" if text is not None else "ocr"
        pages = self._pages.prepare(data, media_type, sha256, straighten=text is None)
        reader = self._reader()
        if text is not None:
            layouts: list[PageLayout] = text
            engine, version = "pdfium", "text layer"
        else:
            layouts = [reader.read(page) for page in pages]
            engine, version = reader.engine, reader.version
        ico, name = self._customers.identity_of(payload.customer_id)
        extracted = self._extractor.extract(
            DocumentLayout(tuple(layouts), engine, version),
            document_id=payload.invoice_id,
            context=Context(customer_ico=ico, customer_name=name),
            channel="digital_pdf" if text is not None else "scan",
            media=_FORMATS[media_type],
        )
        extracted = enrich(extracted, payload.customer_id, self._suppliers)
        handwritten = text is None or self._text.scanned(data)
        note, readings, crop = (
            self._note(pages[0], layouts[0], reader) if handwritten else (None, [], None)
        )

        page_keys = tuple(
            self._storage.put(_jpeg(p.image), owner=payload.customer_id, extension="jpg").key
            for p in pages
        )
        layout = DocumentLayout(tuple(layouts), engine, version)
        layout_key = self._storage.put(
            json.dumps(layout.to_json(), separators=(",", ":")).encode(),
            owner=payload.customer_id,
            extension="json",
        ).key
        note_key = (
            self._storage.put(_png(crop), owner=payload.customer_id, extension="png").key
            if crop is not None
            else None
        )
        with self._uow() as uow:
            at = uow.clock.now()
            fields = extracted.document
            issue = fields.invoice.issue_date
            year = (issue or local_date(at)).year
            next_number, used = counter_hint(uow, payload.customer_id, year)
            if note is not None:
                note = suggest(
                    note,
                    readings,
                    issue_date=issue,
                    today=local_date(at),
                    budget_year=year,
                    next_number=next_number,
                    used=used,
                )
            extraction = Extraction.recorded(
                uow.ids.new(),
                customer_id=payload.customer_id,
                document_id=payload.document_id,
                invoice_id=payload.invoice_id,
                engine=engine,
                engine_version=version,
                source=source,
                document=fields,
                evidence=extracted.evidence,
                warnings=extracted.warnings,
                note=note,
                page_keys=page_keys,
                layout_key=layout_key,
                note_key=note_key,
                duration_ms=round((time.perf_counter() - started) * 1000),
                at=at,
            )
            if not complete_extraction(
                job.request,
                uow,
                payload.customer_id,
                payload.invoice_id,
                job.job_id,
                fields,
                channel="digital_pdf" if text is not None else "scan",
            ):
                return {"outcome": "skipped"}
            uow.extractions.add(extraction)
            uow.audit.record(
                job.request,
                "document.extracted",
                target_type="document",
                target_id=payload.document_id,
                customer_id=payload.customer_id,
                details={
                    "extraction_id": extraction.id,
                    "engine": engine,
                    "source": source,
                    "pages": len(pages),
                    "duration_ms": extraction.duration_ms,
                },
            )
            uow.commit()
        return {"outcome": "extracted", "extraction_id": extraction.id}

    def _note(
        self, page: PageImage, layout: PageLayout, reader: DocumentReader
    ) -> tuple[NoteSuggestions | None, list[str], Image.Image | None]:
        """The note of the first page: of a scan, or of a scanned page with a text layer
        (plan §8.2, "Digital PDFs"); a billing system's PDF has none."""
        region = self._locator.locate(page.image, layout)
        note, readings = note_readings(page, layout, self._locator, reader, region=region)
        b = region.box
        return note, readings, page.image.crop((b.x0, b.y0, b.x1, b.y1))


def retry_extraction(
    ctx: RequestContext, uow: IntakeUnitOfWork, customer_id: str, invoice_id: str
) -> str:
    """Reads a failed invoice's document again; returns the job's ID."""
    ctx.require(Permission.INVOICES_PROCESS, customer_id)
    with uow:
        document_id = failed_extraction_document(uow, customer_id, invoice_id)
        if document_id is None:
            raise InvalidState(f"invoice {invoice_id} has no failed extraction to retry")
        payload = ExtractDocument(
            customer_id=customer_id, document_id=document_id, invoice_id=invoice_id
        )
        job_id = uow.queue.enqueue(
            EXTRACT_JOB, payload.model_dump(), customer_id=customer_id, created_by=ctx.actor_id
        )
        restart_extraction(ctx, uow, customer_id, invoice_id, job_id)
        uow.commit()
    return job_id
