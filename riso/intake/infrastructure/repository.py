"""The intake repositories on SQLAlchemy."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from riso.intake.domain import Document, MediaType
from riso.intake.infrastructure.orm import DocumentRow
from riso.shared.errors import NotFound
from riso.shared.uow import UnitOfWork


def _document(row: DocumentRow) -> Document:
    return Document(
        id=row.id,
        customer_id=row.customer_id,
        sha256=row.sha256,
        filename=row.filename,
        media_type=MediaType(row.media_type),
        size=row.size,
        pages=row.pages,
        storage_key=row.storage_key,
        uploaded_at=row.uploaded_at,
        uploaded_by=row.uploaded_by,
    )


class SqlDocumentRepository:
    def __init__(self, session: Session, uow: UnitOfWork) -> None:
        self._session = session
        self._uow = uow

    def add(self, document: Document) -> None:
        self._session.add(
            DocumentRow(
                id=document.id,
                customer_id=document.customer_id,
                sha256=document.sha256,
                filename=document.filename,
                media_type=document.media_type.value,
                size=document.size,
                pages=document.pages,
                storage_key=document.storage_key,
                uploaded_at=document.uploaded_at,
                uploaded_by=document.uploaded_by,
            )
        )
        self._session.flush()
        self._uow.track(document)

    def get(self, customer_id: str, document_id: str) -> Document:
        row = self._session.scalar(
            select(DocumentRow).where(
                DocumentRow.id == document_id, DocumentRow.customer_id == customer_id
            )
        )
        if row is None:
            raise NotFound(f"no document {document_id}")
        return _document(row)

    def by_sha256(self, customer_id: str, sha256: str) -> Document | None:
        row = self._session.scalar(
            select(DocumentRow).where(
                DocumentRow.customer_id == customer_id, DocumentRow.sha256 == sha256
            )
        )
        return None if row is None else _document(row)

    def of_customer(self, customer_id: str) -> list[Document]:
        rows = self._session.scalars(
            select(DocumentRow)
            .where(DocumentRow.customer_id == customer_id)
            .order_by(DocumentRow.uploaded_at.desc(), DocumentRow.id.desc())
        )
        return [_document(row) for row in rows]
