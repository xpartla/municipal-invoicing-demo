"""The intake context: incoming documents: uploads and their files, duplicate blocking, OCR of
scans, the text layer of digital PDFs, e-invoice XML, and the extraction that turns a document
into an InvoiceDocument. Main aggregates: Document, Extraction. This module is the context's
public surface: other contexts import only what it exports (its application API), never its
domain, infrastructure or api modules. See plan §4.2 and guide §6.1."""

from riso.intake.application import (
    DocumentView,
    IntakeUnitOfWork,
    customer_documents,
)
from riso.intake.domain.units import code_of, unit_of

__all__ = ["DocumentView", "IntakeUnitOfWork", "code_of", "customer_documents", "unit_of"]
