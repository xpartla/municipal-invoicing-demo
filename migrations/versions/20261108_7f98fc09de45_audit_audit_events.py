"""audit: audit events

Revision ID: 7f98fc09de45
Revises: 262ea3a89033
Create Date: 2026-11-08 15:34:33.443804
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7f98fc09de45"
down_revision: str | Sequence[str] | None = "262ea3a89033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("at", sa.DateTime(), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=True),
        sa.Column("real_actor_id", sa.String(length=36), nullable=True),
        sa.Column("customer_id", sa.String(length=36), nullable=True),
        sa.Column("target_type", sa.String(length=40), nullable=True),
        sa.Column("target_id", sa.String(length=36), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_audit_events_action_at"), ["action", "at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_audit_events_actor_id_at"), ["actor_id", "at"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_audit_events_at"), ["at"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_audit_events_customer_id_at"), ["customer_id", "at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_audit_events_real_actor_id_at"), ["real_actor_id", "at"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_audit_events_real_actor_id_at"))
        batch_op.drop_index(batch_op.f("ix_audit_events_customer_id_at"))
        batch_op.drop_index(batch_op.f("ix_audit_events_at"))
        batch_op.drop_index(batch_op.f("ix_audit_events_actor_id_at"))
        batch_op.drop_index(batch_op.f("ix_audit_events_action_at"))

    op.drop_table("audit_events")
