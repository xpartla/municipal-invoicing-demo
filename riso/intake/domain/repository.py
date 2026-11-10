"""The intake context's repositories."""

from typing import Protocol

from riso.intake.domain.document import Document
from riso.intake.domain.extraction import Extraction


class DocumentRepository(Protocol):
    def add(self, document: Document) -> None: ...

    def get(self, customer_id: str, document_id: str) -> Document:
        """Raises `NotFound` when the customer has no such document."""
        ...

    def by_sha256(self, customer_id: str, sha256: str) -> Document | None:
        """The customer's document with this content, if it has one."""
        ...

    def of_customer(self, customer_id: str) -> list[Document]:
        """Every document of the customer, the newest first."""
        ...


class ExtractionRepository(Protocol):
    def add(self, extraction: Extraction) -> None: ...

    def latest(self, customer_id: str, document_id: str) -> Extraction | None:
        """The document's newest extraction, if it was read."""
        ...
