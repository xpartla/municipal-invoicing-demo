"""The identity tables: `users` and `memberships` (plan §11)."""

from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from riso.platform.db import Base, UtcDateTime


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(254), unique=True)
    """The login email, normalised; NULL once purged."""
    notification_email: Mapped[str | None] = mapped_column(String(254))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    password_changed_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    locked_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    deleted_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    purged_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class MembershipRow(Base):
    """A user's role in a customer, a provider or the platform. The scope ID points at a
    customer or a provider by kind, so it has no foreign key; purging a customer or removing a
    provider deals with its memberships explicitly."""

    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "scope_kind", "scope_id"),
        Index(None, "scope_kind", "scope_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # Indexed by the unique constraint, which starts with it.
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    scope_kind: Mapped[str] = mapped_column(String(16))
    scope_id: Mapped[str | None] = mapped_column(String(36))
    role: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    deactivated_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
