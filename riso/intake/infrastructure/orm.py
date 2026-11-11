"""The intake tables (plan §11): `documents`, one row per uploaded file of a customer, unique
by its content (SHA-256) per customer, and `extractions`, each reading of a document. Purging
the customer deletes their rows."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from riso.platform.db import Base, UtcDateTime


class DocumentRow(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("customer_id", "sha256"),
        Index(None, "customer_id", "uploaded_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"))
    sha256: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(200))
    media_type: Mapped[str] = mapped_column(String(40))
    size: Mapped[int] = mapped_column(Integer)
    pages: Mapped[int | None] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(160))
    uploaded_at: Mapped[datetime] = mapped_column(UtcDateTime)
    uploaded_by: Mapped[str | None] = mapped_column(String(36))


class ExtractionRow(Base):
    """One reading of a document: the engine, the fields as read with their confidences and
    where each was read, the warnings, the note's suggestions, and the keys of the stored
    page images, layout and note crop."""

    __tablename__ = "extractions"
    __table_args__ = (
        Index(None, "customer_id", "document_id"),
        Index(None, "customer_id", "invoice_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"))
    document_id: Mapped[str] = mapped_column(String(36))
    invoice_id: Mapped[str] = mapped_column(String(36))
    engine: Mapped[str] = mapped_column(String(32))
    engine_version: Mapped[str] = mapped_column(String(80))
    source: Mapped[str] = mapped_column(String(16))
    document: Mapped[dict[str, Any]] = mapped_column(JSON)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON)
    warnings: Mapped[list[str]] = mapped_column(JSON)
    note: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    page_keys: Mapped[list[str]] = mapped_column(JSON)
    layout_key: Mapped[str] = mapped_column(String(160))
    note_key: Mapped[str | None] = mapped_column(String(160))
    duration_ms: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
