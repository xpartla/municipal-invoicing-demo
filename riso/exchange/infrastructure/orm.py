"""The exchange tables (plan §11): `import_runs`, `mapping_templates` and `export_runs`.

A run belongs to a customer, or to the platform (a global list's import, `customer_id`
NULL); purging the customer deletes its runs. The read options, the mapping and the dry
run's report are JSON validated by their Pydantic models when read back.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from riso.platform.db import Base, UtcDateTime


class ImportRunRow(Base):
    __tablename__ = "import_runs"
    __table_args__ = (Index(None, "customer_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"))
    import_type: Mapped[str] = mapped_column(String(32))
    year: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(16))
    file_key: Mapped[str] = mapped_column(String(160))
    file_sha256: Mapped[str] = mapped_column(String(64))
    file_name: Mapped[str] = mapped_column(String(255))
    file_size: Mapped[int] = mapped_column(Integer)
    file_format: Mapped[str] = mapped_column(String(8))
    options: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    mapping: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    template_id: Mapped[str | None] = mapped_column(String(36))
    report: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    based_on_version_id: Mapped[str | None] = mapped_column(String(36))
    job_id: Mapped[str | None] = mapped_column(String(36))
    applying: Mapped[bool] = mapped_column(Boolean)
    errors_confirmed: Mapped[bool] = mapped_column(Boolean)
    version_id: Mapped[str | None] = mapped_column(String(36))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    created_by: Mapped[str | None] = mapped_column(String(36))
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime)


class MappingTemplateRow(Base):
    """A stored template: global (no owner), a provider's or a customer's. Removing the
    provider or purging the customer deletes its templates."""

    __tablename__ = "mapping_templates"
    __table_args__ = (
        Index(None, "customer_id", "import_type"),
        Index(None, "provider_id", "import_type"),
        Index(None, "scope", "import_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scope: Mapped[str] = mapped_column(String(16))
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"))
    provider_id: Mapped[str | None] = mapped_column(
        ForeignKey("service_providers.id", ondelete="CASCADE")
    )
    import_type: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(120))
    signature: Mapped[str] = mapped_column(String(16))
    mapping: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    created_by: Mapped[str | None] = mapped_column(String(36))
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime)


class ExportRunRow(Base):
    """An export of booked invoices (plan §7.4): what was asked for, the IDs found, and the
    file once the job wrote it. Purging the customer deletes its runs."""

    __tablename__ = "export_runs"
    __table_args__ = (Index(None, "customer_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"))
    format: Mapped[str] = mapped_column(String(8))
    state: Mapped[str] = mapped_column(String(16))
    scope: Mapped[dict[str, Any]] = mapped_column(JSON)
    invoice_ids: Mapped[list[str]] = mapped_column(JSON)
    job_id: Mapped[str | None] = mapped_column(String(36))
    file_key: Mapped[str | None] = mapped_column(String(160))
    file_sha256: Mapped[str | None] = mapped_column(String(64))
    file_name: Mapped[str | None] = mapped_column(String(255))
    file_size: Mapped[int | None] = mapped_column(Integer)
    invoices: Mapped[int] = mapped_column(Integer)
    rows: Mapped[int] = mapped_column(Integer)
    again: Mapped[int] = mapped_column(Integer)
    skipped: Mapped[list[str]] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    created_by: Mapped[str | None] = mapped_column(String(36))
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime)
