"""invoicing: invoices, lines and history

Revision ID: 0539a840ea17
Revises: 1e5202239458
Create Date: 2026-11-09 17:54:04.974627
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0539a840ea17"
down_revision: str | Sequence[str] | None = "1e5202239458"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "invoices",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("customer_id", sa.String(length=36), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=True),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("job_id", sa.String(length=36), nullable=True),
        sa.Column("fields", sa.JSON(), nullable=True),
        sa.Column("extraction_error", sa.Text(), nullable=True),
        sa.Column("duplicate_of", sa.String(length=36), nullable=True),
        sa.Column("proposal", sa.JSON(), nullable=True),
        sa.Column("basis", sa.JSON(), nullable=True),
        sa.Column("coding_error", sa.Text(), nullable=True),
        sa.Column("needs_review", sa.Boolean(), nullable=False),
        sa.Column("booking", sa.JSON(), nullable=True),
        sa.Column("paid_on", sa.Date(), nullable=True),
        sa.Column("discard_reason", sa.Text(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
        sa.Column("uploaded_by", sa.String(length=36), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("checked_at", sa.DateTime(), nullable=True),
        sa.Column("coded_at", sa.DateTime(), nullable=True),
        sa.Column("booked_at", sa.DateTime(), nullable=True),
        sa.Column("exported_at", sa.DateTime(), nullable=True),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("discarded_at", sa.DateTime(), nullable=True),
        sa.Column("supplier_ico", sa.String(length=8), nullable=True),
        sa.Column("supplier_name", sa.String(length=255), nullable=True),
        sa.Column("invoice_number", sa.String(length=64), nullable=True),
        sa.Column("variable_symbol", sa.String(length=32), nullable=True),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("supply_date", sa.Date(), nullable=True),
        sa.Column("booking_date", sa.Date(), nullable=True),
        sa.Column("series", sa.String(length=16), nullable=True),
        sa.Column("document_number", sa.String(length=40), nullable=True),
        sa.Column("gross_cents", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_invoices_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invoices")),
    )
    with op.batch_alter_table("invoices", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_invoices_customer_id_booking_date"),
            ["customer_id", "booking_date"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_invoices_customer_id_document_number"),
            ["customer_id", "document_number"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_invoices_customer_id_state"), ["customer_id", "state"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_invoices_customer_id_supplier_ico"),
            ["customer_id", "supplier_ico"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_invoices_customer_id_uploaded_at"),
            ["customer_id", "uploaded_at"],
            unique=False,
        )

    op.create_table(
        "invoice_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("customer_id", sa.String(length=36), nullable=False),
        sa.Column("invoice_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("at", sa.DateTime(), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=True),
        sa.Column("real_actor_id", sa.String(length=36), nullable=True),
        sa.Column("from_state", sa.String(length=24), nullable=True),
        sa.Column("to_state", sa.String(length=24), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_invoice_events_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["invoices.id"],
            name=op.f("fk_invoice_events_invoice_id_invoices"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invoice_events")),
    )
    with op.batch_alter_table("invoice_events", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_invoice_events_customer_id_invoice_id_at"),
            ["customer_id", "invoice_id", "at"],
            unique=False,
        )

    op.create_table(
        "invoice_lines",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("customer_id", sa.String(length=36), nullable=False),
        sa.Column("invoice_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("budget_key", sa.String(length=32), nullable=False),
        sa.Column("ek", sa.String(length=8), nullable=False),
        sa.Column("zdroj", sa.String(length=8), nullable=False),
        sa.Column("oddiel", sa.String(length=4), nullable=False),
        sa.Column("trieda", sa.String(length=4), nullable=False),
        sa.Column("analytika", sa.String(length=8), nullable=False),
        sa.Column("md", sa.String(length=16), nullable=False),
        sa.Column("dal", sa.String(length=16), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_invoice_lines_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["invoices.id"],
            name=op.f("fk_invoice_lines_invoice_id_invoices"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invoice_lines")),
    )
    with op.batch_alter_table("invoice_lines", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_invoice_lines_customer_id_budget_key"),
            ["customer_id", "budget_key"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_invoice_lines_customer_id_dal"), ["customer_id", "dal"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_invoice_lines_customer_id_invoice_id"),
            ["customer_id", "invoice_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_invoice_lines_customer_id_md"), ["customer_id", "md"], unique=False
        )

    with op.batch_alter_table("used_numbers", schema=None) as batch_op:
        batch_op.add_column(sa.Column("requested_sequence", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("used_numbers", schema=None) as batch_op:
        batch_op.drop_column("requested_sequence")

    with op.batch_alter_table("invoice_lines", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_invoice_lines_customer_id_md"))
        batch_op.drop_index(batch_op.f("ix_invoice_lines_customer_id_invoice_id"))
        batch_op.drop_index(batch_op.f("ix_invoice_lines_customer_id_dal"))
        batch_op.drop_index(batch_op.f("ix_invoice_lines_customer_id_budget_key"))

    op.drop_table("invoice_lines")
    with op.batch_alter_table("invoice_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_invoice_events_customer_id_invoice_id_at"))

    op.drop_table("invoice_events")
    with op.batch_alter_table("invoices", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_invoices_customer_id_uploaded_at"))
        batch_op.drop_index(batch_op.f("ix_invoices_customer_id_supplier_ico"))
        batch_op.drop_index(batch_op.f("ix_invoices_customer_id_state"))
        batch_op.drop_index(batch_op.f("ix_invoices_customer_id_document_number"))
        batch_op.drop_index(batch_op.f("ix_invoices_customer_id_booking_date"))

    op.drop_table("invoices")
