"""identity: tokens

Revision ID: 262ea3a89033
Revises: 46bcc39b24fe
Create Date: 2026-11-08 15:24:04.265184
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "262ea3a89033"
down_revision: str | Sequence[str] | None = "46bcc39b24fe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_tokens_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_tokens_token_hash")),
    )
    with op.batch_alter_table("tokens", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_tokens_user_id_kind"), ["user_id", "kind"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("tokens", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_tokens_user_id_kind"))

    op.drop_table("tokens")
