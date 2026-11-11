"""The intake repositories on SQLAlchemy."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from riso.contracts import InvoiceDocument
from riso.intake.domain import Document, MediaType
from riso.intake.domain.extract import Evidence
from riso.intake.domain.extraction import Extraction
from riso.intake.domain.layout import Box
from riso.intake.domain.note import NoteSuggestions, Suggestion
from riso.intake.infrastructure.orm import DocumentRow, ExtractionRow
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


def _note_json(note: NoteSuggestions | None) -> dict[str, Any] | None:
    if note is None:
        return None

    def suggestions(items: tuple[Suggestion, ...]) -> list[dict[str, Any]]:
        return [
            {
                "value": s.value,
                "source": s.source,
                "plausible": s.plausible,
                "reasons": list(s.reasons),
            }
            for s in items
        ]

    return {
        "page": note.page,
        "box": note.box.to_list(),
        "found": note.found,
        "date": suggestions(note.date),
        "number": suggestions(note.number),
    }


def _note(data: dict[str, Any] | None) -> NoteSuggestions | None:
    if data is None:
        return None

    def suggestions(items: list[dict[str, Any]]) -> tuple[Suggestion, ...]:
        return tuple(
            Suggestion(i["value"], i["source"], bool(i["plausible"]), tuple(i["reasons"]))
            for i in items
        )

    return NoteSuggestions(
        int(data["page"]),
        Box.of(data["box"]),
        bool(data["found"]),
        suggestions(data["date"]),
        suggestions(data["number"]),
    )


def _extraction(row: ExtractionRow) -> Extraction:
    return Extraction(
        id=row.id,
        customer_id=row.customer_id,
        document_id=row.document_id,
        invoice_id=row.invoice_id,
        engine=row.engine,
        engine_version=row.engine_version,
        source="text_layer" if row.source == "text_layer" else "ocr",
        document=InvoiceDocument.model_validate(row.document),
        evidence={
            path: Evidence(int(e["page"]), Box.of(e["box"]), str(e["text"]))
            for path, e in row.evidence.items()
        },
        warnings=tuple(row.warnings),
        note=_note(row.note),
        page_keys=tuple(row.page_keys),
        layout_key=row.layout_key,
        note_key=row.note_key,
        duration_ms=row.duration_ms,
        created_at=row.created_at,
    )


class SqlExtractionRepository:
    def __init__(self, session: Session, uow: UnitOfWork) -> None:
        self._session = session
        self._uow = uow

    def add(self, extraction: Extraction) -> None:
        self._session.add(
            ExtractionRow(
                id=extraction.id,
                customer_id=extraction.customer_id,
                document_id=extraction.document_id,
                invoice_id=extraction.invoice_id,
                engine=extraction.engine,
                engine_version=extraction.engine_version,
                source=extraction.source,
                document=extraction.document.model_dump(mode="json"),
                evidence={
                    path: {"page": e.page, "box": e.box.to_list(), "text": e.text}
                    for path, e in extraction.evidence.items()
                },
                warnings=list(extraction.warnings),
                note=_note_json(extraction.note),
                page_keys=list(extraction.page_keys),
                layout_key=extraction.layout_key,
                note_key=extraction.note_key,
                duration_ms=extraction.duration_ms,
                created_at=extraction.created_at,
            )
        )
        self._session.flush()
        self._uow.track(extraction)

    def latest(self, customer_id: str, document_id: str) -> Extraction | None:
        row = self._session.scalar(
            select(ExtractionRow)
            .where(
                ExtractionRow.customer_id == customer_id,
                ExtractionRow.document_id == document_id,
            )
            .order_by(ExtractionRow.id.desc())
            .limit(1)
        )
        return None if row is None else _extraction(row)
