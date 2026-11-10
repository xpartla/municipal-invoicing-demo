"""invoicing: number series and supplier memory

Revision ID: 1e5202239458
Revises: 925e62bca11c
Create Date: 2026-11-09 17:33:04.279440
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "1e5202239458"
down_revision: str | Sequence[str] | None = "925e62bca11c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "number_series",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("customer_id", sa.String(length=36), nullable=False),
        sa.Column("series", sa.String(length=16), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("pattern", sa.String(length=40), nullable=False),
        sa.Column("last_used", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_number_series_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_number_series")),
        sa.UniqueConstraint(
            "customer_id", "series", "year", name=op.f("uq_number_series_customer_id_series_year")
        ),
    )
    op.create_table(
        "suppliers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("customer_id", sa.String(length=36), nullable=False),
        sa.Column("ico", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_suppliers_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_suppliers")),
        sa.UniqueConstraint("customer_id", "ico", name=op.f("uq_suppliers_customer_id_ico")),
    )
    op.create_table(
        "precedents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("customer_id", sa.String(length=36), nullable=False),
        sa.Column("supplier_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("document_number", sa.String(length=40), nullable=True),
        sa.Column("booking_date", sa.Date(), nullable=True),
        sa.Column("amount_cents", sa.Integer(), nullable=True),
        sa.Column("variable_symbol", sa.String(length=40), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("invoice_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_precedents_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["suppliers.id"],
            name=op.f("fk_precedents_supplier_id_suppliers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_precedents")),
    )
    with op.batch_alter_table("precedents", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_precedents_customer_id_invoice_id"),
            ["customer_id", "invoice_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_precedents_customer_id_supplier_id_position"),
            ["customer_id", "supplier_id", "position"],
            unique=False,
        )

    op.create_table(
        "used_numbers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("customer_id", sa.String(length=36), nullable=False),
        sa.Column("series_id", sa.String(length=36), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=True),
        sa.Column("number", sa.String(length=40), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("invoice_id", sa.String(length=36), nullable=True),
        sa.Column("supply_date", sa.Date(), nullable=True),
        sa.Column("received_at", sa.DateTime(), nullable=True),
        sa.Column("frozen", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_used_numbers_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["number_series.id"],
            name=op.f("fk_used_numbers_series_id_number_series"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_used_numbers")),
        sa.UniqueConstraint(
            "customer_id", "number", name=op.f("uq_used_numbers_customer_id_number")
        ),
        sa.UniqueConstraint(
            "series_id", "sequence", name=op.f("uq_used_numbers_series_id_sequence")
        ),
    )
    with op.batch_alter_table("used_numbers", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_used_numbers_customer_id_invoice_id"),
            ["customer_id", "invoice_id"],
            unique=False,
        )

    op.create_table(
        "precedent_lines",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("customer_id", sa.String(length=36), nullable=False),
        sa.Column("precedent_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("budget_key", sa.String(length=32), nullable=False),
        sa.Column("md", sa.String(length=16), nullable=False),
        sa.Column("dal", sa.String(length=16), nullable=False),
        sa.Column("budget_text", sa.Text(), nullable=False),
        sa.Column("posting_text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_precedent_lines_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["precedent_id"],
            ["precedents.id"],
            name=op.f("fk_precedent_lines_precedent_id_precedents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_precedent_lines")),
    )
    with op.batch_alter_table("precedent_lines", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_precedent_lines_customer_id_precedent_id_position"),
            ["customer_id", "precedent_id", "position"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("precedent_lines", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_precedent_lines_customer_id_precedent_id_position"))

    op.drop_table("precedent_lines")
    with op.batch_alter_table("used_numbers", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_used_numbers_customer_id_invoice_id"))

    op.drop_table("used_numbers")
    with op.batch_alter_table("precedents", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_precedents_customer_id_supplier_id_position"))
        batch_op.drop_index(batch_op.f("ix_precedents_customer_id_invoice_id"))

    op.drop_table("precedents")
    op.drop_table("suppliers")
    op.drop_table("number_series")
