"""The tenancy tables: `service_providers`, `customers`, `provider_assignments` and
`customer_parameters` (plan §11). Customer-owned tables have `customer_id` first in their key
or index."""

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from riso.platform.db import Base, UtcDateTime


class ServiceProviderRow(Base):
    __tablename__ = "service_providers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    ico: Mapped[str | None] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    removed_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class CustomerRow(Base):
    __tablename__ = "customers"
    __table_args__ = (Index(None, "ico", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    ico: Mapped[str] = mapped_column(String(8))
    dic: Mapped[str | None] = mapped_column(String(10))
    street: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(10))
    country: Mapped[str | None] = mapped_column(String(2))
    iban: Mapped[str | None] = mapped_column(String(34))
    variable_number: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    deleted_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class ProviderAssignmentRow(Base):
    """A customer's one service provider (plan §2 decision 4): the customer is the key."""

    __tablename__ = "provider_assignments"

    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), primary_key=True
    )
    provider_id: Mapped[str] = mapped_column(ForeignKey("service_providers.id"), index=True)


class CustomerParametersRow(Base):
    __tablename__ = "customer_parameters"

    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), primary_key=True
    )
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    vat_payer: Mapped[bool] = mapped_column(Boolean)
    default_zdroj: Mapped[str] = mapped_column(String(4))
    default_series: Mapped[str] = mapped_column(String(50))
    default_dal: Mapped[str] = mapped_column(String(7))
    canteen_series: Mapped[str] = mapped_column(String(50))
    canteen_dal: Mapped[str] = mapped_column(String(7))
