"""The codelists tables (plan §11): `codelist_versions` and one typed entry table per kind.

Every entry table is keyed by its version and the entry's position in it, so a list comes
back in the order it was stored (the reference bundle's order). `entry_key` is the entry's
derived key, unique within its version. The customer lists' tables carry `customer_id` with
an index that starts with it; the global lists' tables have no customer. Deleting a version,
or purging its customer, deletes its entries.

Amounts are integer cents.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from riso.platform.db import Base, UtcDateTime


class CodeListVersionRow(Base):
    __tablename__ = "codelist_versions"
    __table_args__ = (
        UniqueConstraint("customer_id", "kind", "year", "number"),
        Index(None, "kind", "year", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"))
    """None for a global list. (A unique constraint ignores NULLs, so the global lists'
    numbering relies on the use case, which runs under BEGIN IMMEDIATE.)"""
    year: Mapped[int] = mapped_column(Integer)
    number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    origin: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    created_by: Mapped[str | None] = mapped_column(String(36))
    entry_count: Mapped[int] = mapped_column(Integer)
    period: Mapped[str | None] = mapped_column(String(7))
    source_name: Mapped[str | None] = mapped_column(String(255))
    source_sha256: Mapped[str | None] = mapped_column(String(64))
    source_rows: Mapped[int | None] = mapped_column(Integer)
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    import_run_id: Mapped[str | None] = mapped_column(String(36))
    note: Mapped[str | None] = mapped_column(String(500))


class _Entry:
    version_id: Mapped[str] = mapped_column(
        ForeignKey("codelist_versions.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_key: Mapped[str] = mapped_column(String(80))
    active: Mapped[bool] = mapped_column(Boolean)


class _CustomerEntry(_Entry):
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"))


class AccountRow(_CustomerEntry, Base):
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("version_id", "entry_key"),
        Index(None, "customer_id", "version_id"),
    )

    su: Mapped[str] = mapped_column(String(3))
    au: Mapped[str] = mapped_column(String(3))
    type: Mapped[str] = mapped_column(String(10))
    activity: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(String(500))
    row: Mapped[int | None] = mapped_column(Integer)


class BudgetPositionRow(_CustomerEntry, Base):
    __tablename__ = "budget_positions"
    __table_args__ = (
        UniqueConstraint("version_id", "entry_key"),
        Index(None, "customer_id", "version_id"),
        Index(None, "customer_id", "ek"),
    )

    direction: Mapped[str] = mapped_column(String(7))
    """expense or income."""
    ek: Mapped[str] = mapped_column(String(6))
    zdroj: Mapped[str] = mapped_column(String(4))
    oddiel: Mapped[str | None] = mapped_column(String(2))
    trieda: Mapped[str | None] = mapped_column(String(3))
    analytika: Mapped[str] = mapped_column(String(3))
    description: Mapped[str | None] = mapped_column(String(500))
    aliases: Mapped[list[str]] = mapped_column(JSON)
    rows: Mapped[list[int]] = mapped_column(JSON)
    approved_cents: Mapped[int | None] = mapped_column(BigInteger)
    adjusted_cents: Mapped[int | None] = mapped_column(BigInteger)


class DocumentSeriesRow(_CustomerEntry, Base):
    __tablename__ = "document_series"
    __table_args__ = (
        UniqueConstraint("version_id", "entry_key"),
        Index(None, "customer_id", "version_id"),
    )

    series_id: Mapped[str] = mapped_column(String(50))
    pattern: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(String(500))
    bank_account: Mapped[str | None] = mapped_column(String(200))


class TransferRow(_CustomerEntry, Base):
    __tablename__ = "transfers"
    __table_args__ = (
        UniqueConstraint("version_id", "entry_key"),
        Index(None, "customer_id", "version_id"),
    )

    name: Mapped[str] = mapped_column(String(500))
    zdroj: Mapped[str] = mapped_column(String(4))
    mock: Mapped[bool] = mapped_column(Boolean)


class CostCentreRow(_CustomerEntry, Base):
    __tablename__ = "cost_centres"
    __table_args__ = (
        UniqueConstraint("version_id", "entry_key"),
        Index(None, "customer_id", "version_id"),
    )

    name: Mapped[str] = mapped_column(String(500))


class _GlobalEntry(_Entry):
    name: Mapped[str] = mapped_column(String(500))


class EkCodeRow(_GlobalEntry, Base):
    __tablename__ = "ek_codes"
    __table_args__ = (UniqueConstraint("version_id", "entry_key"),)


class CofogFunctionRow(_GlobalEntry, Base):
    __tablename__ = "cofog_functions"
    __table_args__ = (UniqueConstraint("version_id", "entry_key"),)


class FundingSourceRow(_GlobalEntry, Base):
    __tablename__ = "funding_sources"
    __table_args__ = (UniqueConstraint("version_id", "entry_key"),)


class FrameworkAccountRow(_GlobalEntry, Base):
    __tablename__ = "framework_accounts"
    __table_args__ = (UniqueConstraint("version_id", "entry_key"),)


class CustomerConventionsRow(Base):
    """A customer's conventions for a year (plan §11): the document as JSON, validated by the
    `Conventions` model on the way in and out."""

    __tablename__ = "customer_conventions"

    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), primary_key=True
    )
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision: Mapped[int] = mapped_column(Integer)
    document: Mapped[dict[str, Any]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime)
    updated_by: Mapped[str | None] = mapped_column(String(36))
