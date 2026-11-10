"""The intake tables (plan §11): `documents`, one row per uploaded file of a customer, unique
by its content (SHA-256) per customer. Purging the customer deletes its rows."""

from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
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
