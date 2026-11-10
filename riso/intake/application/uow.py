"""The unit of work the intake use cases need: its documents, and the invoicing context's
repositories and the job queue on the same transaction, so a document, its invoice and its
extraction job are stored together or not at all."""

from typing import Protocol

from riso.intake.domain import DocumentRepository
from riso.invoicing import InvoicingUnitOfWork
from riso.jobs import JobQueue


class IntakeUnitOfWork(InvoicingUnitOfWork, Protocol):
    @property
    def documents(self) -> DocumentRepository: ...

    @property
    def queue(self) -> JobQueue: ...
