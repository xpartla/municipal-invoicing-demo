"""Use cases, views and ports of the intake context: uploads and their documents, and the
extraction job."""

from riso.intake.application.extraction import (
    EXTRACT_JOB,
    Customers,
    ExtractDocument,
    ExtractionJobs,
    retry_extraction,
)
from riso.intake.application.ports import (
    DocumentReader,
    EInvoiceReader,
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
from riso.intake.application.views import (
    DocumentFile,
    DocumentView,
    EInvoiceDetail,
    ExtractionView,
    UploadOutcome,
    einvoice_detail,
    extraction_image,
    get_extraction,
)

__all__ = [
    "EXTRACT_JOB",
    "MAX_FILES",
    "Customers",
    "DocumentFile",
    "DocumentReader",
    "DocumentView",
    "EInvoiceDetail",
    "EInvoiceReader",
    "ExtractDocument",
    "ExtractionJobs",
    "ExtractionView",
    "IntakeUnitOfWork",
    "PageCounter",
    "PageImage",
    "PagePreparer",
    "TextLayer",
    "UploadOutcome",
    "UploadedFile",
    "customer_documents",
    "document_file",
    "einvoice_detail",
    "extraction_image",
    "get_document",
    "get_extraction",
    "retry_extraction",
    "upload_documents",
]
