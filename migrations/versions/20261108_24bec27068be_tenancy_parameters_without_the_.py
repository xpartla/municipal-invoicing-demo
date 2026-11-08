"""tenancy: parameters without the reference period

Revision ID: 24bec27068be
Revises: e2331b00d3d2
Create Date: 2026-11-08 22:27:23.246756
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "24bec27068be"
down_revision: str | Sequence[str] | None = "e2331b00d3d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("customer_parameters", schema=None) as batch_op:
        batch_op.drop_column("reference_period")


def downgrade() -> None:
    with op.batch_alter_table("customer_parameters", schema=None) as batch_op:
        # The period is the code lists' since P2-M2; the year's January stands in for it.
        batch_op.add_column(
            sa.Column(
                "reference_period", sa.VARCHAR(length=7), nullable=False, server_default="2000-01"
            )
        )
    op.execute("UPDATE customer_parameters SET reference_period = CAST(year AS VARCHAR) || '-01'")
