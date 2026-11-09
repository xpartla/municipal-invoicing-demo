"""exchange: mapping templates

The `mapping_templates` table (plan §9.2 step 5, §11): saved mappings, global or owned by a
provider or a customer. The built-in templates live in the code.

Revision ID: 925e62bca11c
Revises: 53623de58cf8
Create Date: 2026-11-09 11:47:10.551040
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "925e62bca11c"
down_revision: str | Sequence[str] | None = "53623de58cf8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mapping_templates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("customer_id", sa.String(length=36), nullable=True),
        sa.Column("provider_id", sa.String(length=36), nullable=True),
        sa.Column("import_type", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("signature", sa.String(length=16), nullable=False),
        sa.Column("mapping", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_mapping_templates_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["service_providers.id"],
            name=op.f("fk_mapping_templates_provider_id_service_providers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mapping_templates")),
    )
    with op.batch_alter_table("mapping_templates", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_mapping_templates_customer_id_import_type"),
            ["customer_id", "import_type"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_mapping_templates_provider_id_import_type"),
            ["provider_id", "import_type"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_mapping_templates_scope_import_type"),
            ["scope", "import_type"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("mapping_templates", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_mapping_templates_scope_import_type"))
        batch_op.drop_index(batch_op.f("ix_mapping_templates_provider_id_import_type"))
        batch_op.drop_index(batch_op.f("ix_mapping_templates_customer_id_import_type"))

    op.drop_table("mapping_templates")
