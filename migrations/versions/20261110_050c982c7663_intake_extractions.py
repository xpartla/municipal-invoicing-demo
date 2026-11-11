"""intake: extractions (each reading of a document)

Revision ID: 050c982c7663
Revises: d3398a9b76dd
Create Date: 2026-11-10 20:48:11.483855
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "050c982c7663"
down_revision: str | Sequence[str] | None = "d3398a9b76dd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "extractions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("customer_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("invoice_id", sa.String(length=36), nullable=False),
        sa.Column("engine", sa.String(length=32), nullable=False),
        sa.Column("engine_version", sa.String(length=80), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("document", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("note", sa.JSON(), nullable=True),
        sa.Column("page_keys", sa.JSON(), nullable=False),
        sa.Column("layout_key", sa.String(length=160), nullable=False),
        sa.Column("note_key", sa.String(length=160), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_extractions_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_extractions")),
    )
    with op.batch_alter_table("extractions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_extractions_customer_id_document_id"),
            ["customer_id", "document_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_extractions_customer_id_invoice_id"),
            ["customer_id", "invoice_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("extractions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_extractions_customer_id_invoice_id"))
        batch_op.drop_index(batch_op.f("ix_extractions_customer_id_document_id"))

    op.drop_table("extractions")
