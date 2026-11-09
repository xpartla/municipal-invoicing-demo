"""The invoicing tables (plan §11): `number_series`, `used_numbers`, `suppliers`,
`precedents` and `precedent_lines`. Each belongs to a customer; purging the customer deletes
its rows.

`used_numbers` holds every number the customer used: the numbers held in a series (with
their sequence) and, without a series, numbers that fit none. A number is unique per
customer, and per series its sequence. Amounts are integer cents.
"""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from riso.platform.db import Base, UtcDateTime


class NumberSeriesRow(Base):
    __tablename__ = "number_series"
    __table_args__ = (UniqueConstraint("customer_id", "series", "year"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"))
    series: Mapped[str] = mapped_column(String(16))
    year: Mapped[int] = mapped_column(Integer)
    pattern: Mapped[str] = mapped_column(String(40))
    last_used: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime)


class UsedNumberRow(Base):
    __tablename__ = "used_numbers"
    __table_args__ = (
        UniqueConstraint("customer_id", "number"),
        UniqueConstraint("series_id", "sequence"),
        Index(None, "customer_id", "invoice_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    """UUIDv7: the order of first use."""
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"))
    series_id: Mapped[str | None] = mapped_column(
        ForeignKey("number_series.id", ondelete="CASCADE")
    )
    sequence: Mapped[int | None] = mapped_column(Integer)
    number: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(16))
    invoice_id: Mapped[str | None] = mapped_column(String(36))
    supply_date: Mapped[date | None] = mapped_column(Date)
    received_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    frozen: Mapped[bool] = mapped_column(Boolean)


class SupplierRow(Base):
    __tablename__ = "suppliers"
    __table_args__ = (UniqueConstraint("customer_id", "ico"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    """UUIDv7: suppliers are read in the order they were added."""
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"))
    ico: Mapped[str] = mapped_column(String(8))
    name: Mapped[str] = mapped_column(String(255))


class PrecedentRow(Base):
    __tablename__ = "precedents"
    __table_args__ = (
        Index(None, "customer_id", "supplier_id", "position"),
        Index(None, "customer_id", "invoice_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"))
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    """0 is the supplier's newest precedent."""
    document_number: Mapped[str | None] = mapped_column(String(40))
    booking_date: Mapped[date | None] = mapped_column(Date)
    amount_cents: Mapped[int | None] = mapped_column(Integer)
    variable_symbol: Mapped[str | None] = mapped_column(String(40))
    source: Mapped[str] = mapped_column(String(16))
    invoice_id: Mapped[str | None] = mapped_column(String(36))
    """The invoice whose booking made it (S8), so unbooking can remove it."""


class PrecedentLineRow(Base):
    __tablename__ = "precedent_lines"
    __table_args__ = (Index(None, "customer_id", "precedent_id", "position"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"))
    precedent_id: Mapped[str] = mapped_column(ForeignKey("precedents.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    budget_key: Mapped[str] = mapped_column(String(32))
    md: Mapped[str] = mapped_column(String(16))
    dal: Mapped[str] = mapped_column(String(16))
    budget_text: Mapped[str] = mapped_column(Text)
    posting_text: Mapped[str] = mapped_column(Text)
