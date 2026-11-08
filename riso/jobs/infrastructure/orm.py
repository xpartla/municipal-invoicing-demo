"""The `jobs` table."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from riso.platform.db import Base, UtcDateTime


class JobRow(Base):
    __tablename__ = "jobs"
    __table_args__ = (Index(None, "status", "run_after"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16))
    attempts: Mapped[int] = mapped_column(Integer)
    max_attempts: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    run_after: Mapped[datetime] = mapped_column(UtcDateTime)
    created_by: Mapped[str | None] = mapped_column(String(36))
    customer_id: Mapped[str | None] = mapped_column(String(36), index=True)
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    locked_by: Mapped[str | None] = mapped_column(String(64))
    locked_until: Mapped[datetime | None] = mapped_column(UtcDateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
