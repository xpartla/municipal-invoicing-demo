"""platform, jobs: mail outbox and jobs

Revision ID: 308b3b9302a0
Revises: 91bf0ba34c08
Create Date: 2026-11-08 13:37:24.595138
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "308b3b9302a0"
down_revision: str | Sequence[str] | None = "91bf0ba34c08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("run_after", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("customer_id", sa.String(length=36), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("locked_by", sa.String(length=64), nullable=True),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
    )
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_jobs_customer_id"), ["customer_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_jobs_status_run_after"), ["status", "run_after"], unique=False
        )

    op.create_table(
        "mail_outbox",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("to_address", sa.String(length=320), nullable=False),
        sa.Column("subject", sa.String(length=300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("template", sa.String(length=100), nullable=False),
        sa.Column("customer_id", sa.String(length=36), nullable=True),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mail_outbox")),
    )
    with op.batch_alter_table("mail_outbox", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_mail_outbox_created_at"), ["created_at"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_mail_outbox_customer_id"), ["customer_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("mail_outbox", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_mail_outbox_customer_id"))
        batch_op.drop_index(batch_op.f("ix_mail_outbox_created_at"))

    op.drop_table("mail_outbox")
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_jobs_status_run_after"))
        batch_op.drop_index(batch_op.f("ix_jobs_customer_id"))

    op.drop_table("jobs")
