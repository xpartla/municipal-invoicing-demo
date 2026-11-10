"""The invoicing tables (plan §11): `invoices` with `invoice_lines` and `invoice_events`,
`number_series`, `used_numbers`, `suppliers`, `precedents` and `precedent_lines`. Each belongs
to a customer; purging the customer deletes its rows.

An invoice keeps its fields, proposal, coding basis and booking as JSON (validated by their
contracts when read back), and copies what the table filters and sorts by into plain columns:
the supplier, the invoice's numbers and dates, the document series, number and booking date,
the gross in cents, and `search_text` (folded for case- and diacritics-insensitive search).
`invoice_lines` holds the lines of the booking, or of the proposal before it, for the filters
by budget key and account.

`used_numbers` holds every number the customer used: the numbers held in a series (with
their sequence) and, without a series, numbers that fit none. A number is unique per
customer, and per series its sequence. Amounts are integer cents.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
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
    requested_sequence: Mapped[int | None] = mapped_column(Integer)
    """The handwritten or typed number the booking asked for (decision 61's order)."""


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


class InvoiceRow(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        Index(None, "customer_id", "state"),
        Index(None, "customer_id", "uploaded_at"),
        Index(None, "customer_id", "booking_date"),
        Index(None, "customer_id", "supplier_ico"),
        Index(None, "customer_id", "document_number"),
        Index(None, "customer_id", "issue_date"),
        Index(None, "customer_id", "due_date"),
        Index(None, "customer_id", "exported_at"),
        Index(None, "customer_id", "paid_on"),
        Index(None, "customer_id", "gross_cents"),
        Index(None, "customer_id", "document_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"))
    channel: Mapped[str] = mapped_column(String(16))
    state: Mapped[str] = mapped_column(String(24))
    document_id: Mapped[str | None] = mapped_column(String(36))
    source_ref: Mapped[str | None] = mapped_column(String(255))
    job_id: Mapped[str | None] = mapped_column(String(36))
    fields: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    extraction_error: Mapped[str | None] = mapped_column(Text)
    duplicate_of: Mapped[str | None] = mapped_column(String(36))
    proposal: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    basis: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    coding_error: Mapped[str | None] = mapped_column(Text)
    needs_review: Mapped[bool] = mapped_column(Boolean)
    booking: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    paid_on: Mapped[date | None] = mapped_column(Date)
    discard_reason: Mapped[str | None] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(UtcDateTime)
    uploaded_by: Mapped[str | None] = mapped_column(String(36))
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime)
    checked_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    coded_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    booked_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    exported_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    paid_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    discarded_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    # Denormalised for the table's filters and sorting.
    supplier_ico: Mapped[str | None] = mapped_column(String(8))
    supplier_name: Mapped[str | None] = mapped_column(String(255))
    invoice_number: Mapped[str | None] = mapped_column(String(64))
    variable_symbol: Mapped[str | None] = mapped_column(String(32))
    issue_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    supply_date: Mapped[date | None] = mapped_column(Date)
    booking_date: Mapped[date | None] = mapped_column(Date)
    series: Mapped[str | None] = mapped_column(String(16))
    document_number: Mapped[str | None] = mapped_column(String(40))
    gross_cents: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str | None] = mapped_column(String(3))
    search_text: Mapped[str] = mapped_column(Text)
    supplier_text: Mapped[str] = mapped_column(Text)
    """The supplier's name and IČO, folded, for the supplier filter's search."""


class InvoiceLineRow(Base):
    __tablename__ = "invoice_lines"
    __table_args__ = (
        Index(None, "customer_id", "invoice_id"),
        Index(None, "customer_id", "budget_key"),
        Index(None, "customer_id", "md"),
        Index(None, "customer_id", "dal"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"))
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    budget_key: Mapped[str] = mapped_column(String(32))
    ek: Mapped[str] = mapped_column(String(8))
    zdroj: Mapped[str] = mapped_column(String(8))
    oddiel: Mapped[str] = mapped_column(String(4))
    trieda: Mapped[str] = mapped_column(String(4))
    analytika: Mapped[str] = mapped_column(String(8))
    md: Mapped[str] = mapped_column(String(16))
    dal: Mapped[str] = mapped_column(String(16))
    amount_cents: Mapped[int] = mapped_column(Integer)


class InvoiceEventRow(Base):
    __tablename__ = "invoice_events"
    __table_args__ = (Index(None, "customer_id", "invoice_id", "at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"))
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(24))
    at: Mapped[datetime] = mapped_column(UtcDateTime)
    actor_id: Mapped[str | None] = mapped_column(String(36))
    real_actor_id: Mapped[str | None] = mapped_column(String(36))
    from_state: Mapped[str | None] = mapped_column(String(24))
    to_state: Mapped[str] = mapped_column(String(24))
    details: Mapped[dict[str, Any]] = mapped_column(JSON)
