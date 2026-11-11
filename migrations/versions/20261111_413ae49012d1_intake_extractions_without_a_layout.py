"""intake: extractions without a layout

An e-invoice's reading has no words with boxes (P2-M6-T05), so `extractions.layout_key`
becomes optional. Going back, those readings get an empty key, which names no stored file.

Revision ID: 413ae49012d1
Revises: 050c982c7663
Create Date: 2026-11-11 09:31:06.196353
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "413ae49012d1"
down_revision: str | Sequence[str] | None = "050c982c7663"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("extractions", schema=None) as batch_op:
        batch_op.alter_column("layout_key", existing_type=sa.VARCHAR(length=160), nullable=True)


def downgrade() -> None:
    op.execute("UPDATE extractions SET layout_key = '' WHERE layout_key IS NULL")
    with op.batch_alter_table("extractions", schema=None) as batch_op:
        batch_op.alter_column("layout_key", existing_type=sa.VARCHAR(length=160), nullable=False)
