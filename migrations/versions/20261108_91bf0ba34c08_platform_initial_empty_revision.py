"""platform: initial empty revision

Revision ID: 91bf0ba34c08
Revises:
Create Date: 2026-11-08 13:26:47.489619
"""

from collections.abc import Sequence

revision: str = "91bf0ba34c08"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
