"""The `extract_document` job (plan §4.6, §4.7): it reads an uploaded document and moves its
invoice to `extracted`, or to `extraction_failed` with the reason. Idempotent: an invoice that
no longer waits for the job is left alone.

Until the reading pipeline is wired in (P2-M5-T07), every extraction fails with the reason
`reader_unavailable`, so an uploaded invoice goes to manual entry.
"""

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict

from riso.intake.application.uow import IntakeUnitOfWork
from riso.invoicing import fail_extraction
from riso.jobs import JobContext, JobRegistry

EXTRACT_JOB = "extract_document"


class ExtractDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: str
    document_id: str
    invoice_id: str


class ExtractionJobs:
    def __init__(self, uow_factory: Callable[[], IntakeUnitOfWork]) -> None:
        self._uow = uow_factory

    def register(self, registry: JobRegistry) -> None:
        registry.register(EXTRACT_JOB, ExtractDocument, self.run)

    def run(self, payload: ExtractDocument, job: JobContext) -> dict[str, Any] | None:
        with self._uow() as uow:
            uow.documents.get(payload.customer_id, payload.document_id)
            failed = fail_extraction(
                job.request,
                uow,
                payload.customer_id,
                payload.invoice_id,
                job.job_id,
                "reader_unavailable",
            )
            uow.commit()
        return {"outcome": "extraction_failed" if failed else "skipped"}
