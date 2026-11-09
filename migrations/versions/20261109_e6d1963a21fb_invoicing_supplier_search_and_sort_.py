"""invoicing: supplier search and sort indexes

Revision ID: e6d1963a21fb
Revises: 0539a840ea17
Create Date: 2026-11-09 18:22:07.830202
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from riso.text import fold

revision: str = "e6d1963a21fb"
down_revision: str | Sequence[str] | None = "0539a840ea17"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("invoices", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("supplier_text", sa.Text(), nullable=False, server_default="")
        )
        batch_op.create_index(
            batch_op.f("ix_invoices_customer_id_due_date"),
            ["customer_id", "due_date"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_invoices_customer_id_exported_at"),
            ["customer_id", "exported_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_invoices_customer_id_gross_cents"),
            ["customer_id", "gross_cents"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_invoices_customer_id_issue_date"),
            ["customer_id", "issue_date"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_invoices_customer_id_paid_on"), ["customer_id", "paid_on"], unique=False
        )
    # Invoices stored before this revision: their supplier's name and IČO, folded.
    invoices = sa.table(
        "invoices",
        sa.column("id", sa.String),
        sa.column("supplier_name", sa.String),
        sa.column("supplier_ico", sa.String),
        sa.column("supplier_text", sa.Text),
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(invoices.c.id, invoices.c.supplier_name, invoices.c.supplier_ico)
    ).all()
    for invoice_id, name, ico in rows:
        text = fold(" ".join(part for part in (name, ico) if part)).casefold()
        connection.execute(
            invoices.update().where(invoices.c.id == invoice_id).values(supplier_text=text)
        )


def downgrade() -> None:
    with op.batch_alter_table("invoices", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_invoices_customer_id_paid_on"))
        batch_op.drop_index(batch_op.f("ix_invoices_customer_id_issue_date"))
        batch_op.drop_index(batch_op.f("ix_invoices_customer_id_gross_cents"))
        batch_op.drop_index(batch_op.f("ix_invoices_customer_id_exported_at"))
        batch_op.drop_index(batch_op.f("ix_invoices_customer_id_due_date"))
        batch_op.drop_column("supplier_text")
