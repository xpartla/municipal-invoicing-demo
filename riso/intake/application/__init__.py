"""Use cases, views and ports of the intake context: uploads and their documents, and the
extraction job."""

from riso.intake.application.extraction import EXTRACT_JOB, ExtractDocument, ExtractionJobs
from riso.intake.application.ports import (
    DocumentReader,
    PageCounter,
    PageImage,
    PagePreparer,
    TextLayer,
)
from riso.intake.application.uow import IntakeUnitOfWork
from riso.intake.application.upload import (
    MAX_FILES,
    UploadedFile,
    customer_documents,
    document_file,
    get_document,
    upload_documents,
)
from riso.intake.application.views import DocumentFile, DocumentView, UploadOutcome

__all__ = [
    "EXTRACT_JOB",
    "MAX_FILES",
    "DocumentFile",
    "DocumentReader",
    "DocumentView",
    "ExtractDocument",
    "ExtractionJobs",
    "IntakeUnitOfWork",
    "PageCounter",
    "PageImage",
    "PagePreparer",
    "TextLayer",
    "UploadOutcome",
    "UploadedFile",
    "customer_documents",
    "document_file",
    "get_document",
    "upload_documents",
]
