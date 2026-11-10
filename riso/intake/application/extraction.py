"""The `extract_document` job (plan §4.6, §4.7): it reads an uploaded document and moves its
invoice to `extracted`, or to `extraction_failed` with the reason. Idempotent: an invoice that
no longer waits for the job is left alone, before anything is read.

The job runs in the worker's thread and the OCR in its own process (`TesseractReader`), so
reading a page never holds a request. A PDF with a usable text layer is read from it, without
OCR (plan §8.2, "Digital PDFs"). Until the field extractor is wired in (P2-M5-T07) the pages
are read and the extraction ends with the reason `not_extracted`.
"""

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict

from riso.intake.application.ports import DocumentReader, PagePreparer, TextLayer
from riso.intake.application.uow import IntakeUnitOfWork
from riso.intake.domain import MediaType
from riso.intake.domain.layout import ReadingFailed
from riso.invoicing import awaits_extraction, fail_extraction
from riso.jobs import JobContext, JobRegistry
from riso.shared.ports import FileStorage

EXTRACT_JOB = "extract_document"


class ExtractDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: str
    document_id: str
    invoice_id: str


class ExtractionJobs:
    def __init__(
        self,
        uow_factory: Callable[[], IntakeUnitOfWork],
        storage: FileStorage,
        reader: Callable[[], DocumentReader],
        pages: PagePreparer,
        text: TextLayer,
    ) -> None:
        self._uow = uow_factory
        self._storage = storage
        self._reader = reader
        self._pages = pages
        self._text = text

    def register(self, registry: JobRegistry) -> None:
        registry.register(EXTRACT_JOB, ExtractDocument, self.run)

    def run(self, payload: ExtractDocument, job: JobContext) -> dict[str, Any] | None:
        with self._uow() as uow:
            if not awaits_extraction(uow, payload.customer_id, payload.invoice_id, job.job_id):
                return {"outcome": "skipped"}
            document = uow.documents.get(payload.customer_id, payload.document_id)
        with self._storage.open(document.storage_key) as handle:
            data = handle.read()
        try:
            layouts = self._text.read(data) if document.media_type is MediaType.PDF else None
            if layouts is None:
                reader = self._reader()
                pages = self._pages.prepare(data, document.media_type, document.sha256)
                layouts = [reader.read(page) for page in pages]
            reason = "not_extracted"
        except ReadingFailed as failed:
            reason = failed.reason
        with self._uow() as uow:
            fail_extraction(
                job.request, uow, payload.customer_id, payload.invoice_id, job.job_id, reason
            )
            uow.commit()
        return {"outcome": "extraction_failed", "reason": reason}
