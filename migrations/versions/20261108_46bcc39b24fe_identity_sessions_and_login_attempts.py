"""identity: sessions and login attempts

Revision ID: 46bcc39b24fe
Revises: 8beddc1a462f
Create Date: 2026-11-08 15:17:25.468542
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "46bcc39b24fe"
down_revision: str | Sequence[str] | None = "8beddc1a462f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "login_attempts",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("last_failure_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_login_attempts")),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("csrf_token", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column("impersonated_user_id", sa.String(length=36), nullable=True),
        sa.Column("impersonation_reason", sa.String(length=500), nullable=True),
        sa.Column("impersonation_started_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["impersonated_user_id"],
            ["users.id"],
            name=op.f("fk_sessions_impersonated_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_sessions_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_sessions_token_hash")),
    )
    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_sessions_impersonated_user_id"), ["impersonated_user_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_sessions_user_id"), ["user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_sessions_user_id"))
        batch_op.drop_index(batch_op.f("ix_sessions_impersonated_user_id"))

    op.drop_table("sessions")
    op.drop_table("login_attempts")
