"""exchange: export runs

Revision ID: 7f22757fa099
Revises: e6d1963a21fb
Create Date: 2026-11-09 18:38:53.560544
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7f22757fa099"
down_revision: str | Sequence[str] | None = "e6d1963a21fb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "export_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("customer_id", sa.String(length=36), nullable=False),
        sa.Column("format", sa.String(length=8), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("invoice_ids", sa.JSON(), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=True),
        sa.Column("file_key", sa.String(length=160), nullable=True),
        sa.Column("file_sha256", sa.String(length=64), nullable=True),
        sa.Column("file_name", sa.String(length=255), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("invoices", sa.Integer(), nullable=False),
        sa.Column("rows", sa.Integer(), nullable=False),
        sa.Column("again", sa.Integer(), nullable=False),
        sa.Column("skipped", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_export_runs_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_export_runs")),
    )
    with op.batch_alter_table("export_runs", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_export_runs_customer_id_created_at"),
            ["customer_id", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("export_runs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_export_runs_customer_id_created_at"))

    op.drop_table("export_runs")
