"""codelists: customer conventions

Revision ID: e2331b00d3d2
Revises: 2280234ea511
Create Date: 2026-11-08 22:22:52.485724
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e2331b00d3d2"
down_revision: str | Sequence[str] | None = "2280234ea511"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customer_conventions",
        sa.Column("customer_id", sa.String(length=36), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("document", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_customer_conventions_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("customer_id", "year", name=op.f("pk_customer_conventions")),
    )


def downgrade() -> None:
    op.drop_table("customer_conventions")
