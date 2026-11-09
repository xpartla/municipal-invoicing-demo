"""exchange: import runs

The `import_runs` table (plan §9.2, §11): one row per uploaded import file, with its
mapping and dry-run report as JSON.

Revision ID: 53623de58cf8
Revises: 24bec27068be
Create Date: 2026-11-09 11:37:18.740798
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "53623de58cf8"
down_revision: str | Sequence[str] | None = "24bec27068be"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "import_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("customer_id", sa.String(length=36), nullable=True),
        sa.Column("import_type", sa.String(length=32), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("file_key", sa.String(length=160), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("file_format", sa.String(length=8), nullable=False),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("mapping", sa.JSON(), nullable=True),
        sa.Column("template_id", sa.String(length=36), nullable=True),
        sa.Column("report", sa.JSON(), nullable=True),
        sa.Column("based_on_version_id", sa.String(length=36), nullable=True),
        sa.Column("job_id", sa.String(length=36), nullable=True),
        sa.Column("applying", sa.Boolean(), nullable=False),
        sa.Column("errors_confirmed", sa.Boolean(), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_import_runs_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_runs")),
    )
    with op.batch_alter_table("import_runs", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_import_runs_customer_id_created_at"),
            ["customer_id", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("import_runs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_import_runs_customer_id_created_at"))

    op.drop_table("import_runs")
