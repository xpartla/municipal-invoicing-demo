"""intake: documents (the uploaded files), and invoices by their document

Revision ID: d3398a9b76dd
Revises: 7f22757fa099
Create Date: 2026-11-10 19:19:10.285018
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d3398a9b76dd"
down_revision: str | Sequence[str] | None = "7f22757fa099"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("customer_id", sa.String(length=36), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=200), nullable=False),
        sa.Column("media_type", sa.String(length=40), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("pages", sa.Integer(), nullable=True),
        sa.Column("storage_key", sa.String(length=160), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
        sa.Column("uploaded_by", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_documents_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
        sa.UniqueConstraint("customer_id", "sha256", name=op.f("uq_documents_customer_id_sha256")),
    )
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_documents_customer_id_uploaded_at"),
            ["customer_id", "uploaded_at"],
            unique=False,
        )

    with op.batch_alter_table("invoices", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_invoices_customer_id_document_id"),
            ["customer_id", "document_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("invoices", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_invoices_customer_id_document_id"))

    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_documents_customer_id_uploaded_at"))

    op.drop_table("documents")
