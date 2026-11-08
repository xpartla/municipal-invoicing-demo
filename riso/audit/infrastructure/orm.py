"""The `audit_events` table: append-only. Nothing in the code updates or deletes a row, and
purging a customer or a user keeps their events (plan §2 decision 51)."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from riso.platform.db import Base, UtcDateTime


class AuditEventRow(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index(None, "customer_id", "at"),
        Index(None, "actor_id", "at"),
        Index(None, "real_actor_id", "at"),
        Index(None, "action", "at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    at: Mapped[datetime] = mapped_column(UtcDateTime, index=True)
    action: Mapped[str] = mapped_column(String(80))
    actor_id: Mapped[str | None] = mapped_column(String(36))
    real_actor_id: Mapped[str | None] = mapped_column(String(36))
    customer_id: Mapped[str | None] = mapped_column(String(36))
    target_type: Mapped[str | None] = mapped_column(String(40))
    target_id: Mapped[str | None] = mapped_column(String(36))
    details: Mapped[dict[str, Any]] = mapped_column(JSON)
    request_id: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(45))
