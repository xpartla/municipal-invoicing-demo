"""The exchange tables (plan §11): `import_runs`.

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
