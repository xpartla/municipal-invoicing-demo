"""invoicing: index on booked_at (the invoice table's "booked in riso" filter, P2-M8-T04)

Revision ID: c4087da190e3
Revises: 413ae49012d1
Create Date: 2026-11-11 22:22:36.980044
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c4087da190e3"
down_revision: str | Sequence[str] | None = "413ae49012d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("invoices", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_invoices_customer_id_booked_at"),
            ["customer_id", "booked_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("invoices", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_invoices_customer_id_booked_at"))
