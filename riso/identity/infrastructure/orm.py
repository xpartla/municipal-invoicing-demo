"""The identity tables: `users`, `memberships`, `sessions`, `login_attempts` and `tokens`
(plan §11)."""

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, UniqueConstraint
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


class SessionRow(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    last_seen_at: Mapped[datetime] = mapped_column(UtcDateTime)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    impersonated_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    impersonation_reason: Mapped[str | None] = mapped_column(String(500))
    impersonation_started_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class LoginAttemptRow(Base):
    """Failed logins per hashed key (`account:…`, `ip:…`)."""

    __tablename__ = "login_attempts"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    failures: Mapped[int] = mapped_column(Integer)
    last_failure_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class TokenRow(Base):
    """Single-use mail tokens, stored as their SHA-256."""

    __tablename__ = "tokens"
    __table_args__ = (Index(None, "user_id", "kind"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime)
    used_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    payload: Mapped[dict[str, str]] = mapped_column(JSON)
