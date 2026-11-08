"""identity, tenancy: users, memberships, customers, providers, assignments, parameters

Revision ID: 8beddc1a462f
Revises: 308b3b9302a0
Create Date: 2026-11-08 15:05:58.570075
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8beddc1a462f"
down_revision: str | Sequence[str] | None = "308b3b9302a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("ico", sa.String(length=8), nullable=False),
        sa.Column("dic", sa.String(length=10), nullable=True),
        sa.Column("street", sa.String(length=200), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("postal_code", sa.String(length=10), nullable=True),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("iban", sa.String(length=34), nullable=True),
        sa.Column("variable_number", sa.String(length=10), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customers")),
    )
    with op.batch_alter_table("customers", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_customers_ico_status"), ["ico", "status"], unique=False
        )

    op.create_table(
        "service_providers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("ico", sa.String(length=8), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("removed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_service_providers")),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("notification_email", sa.String(length=254), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("password_changed_at", sa.DateTime(), nullable=True),
        sa.Column("locked_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("purged_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "customer_parameters",
        sa.Column("customer_id", sa.String(length=36), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("vat_payer", sa.Boolean(), nullable=False),
        sa.Column("reference_period", sa.String(length=7), nullable=False),
        sa.Column("default_zdroj", sa.String(length=4), nullable=False),
        sa.Column("default_series", sa.String(length=50), nullable=False),
        sa.Column("default_dal", sa.String(length=7), nullable=False),
        sa.Column("canteen_series", sa.String(length=50), nullable=False),
        sa.Column("canteen_dal", sa.String(length=7), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_customer_parameters_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("customer_id", "year", name=op.f("pk_customer_parameters")),
    )
    op.create_table(
        "memberships",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("scope_kind", sa.String(length=16), nullable=False),
        sa.Column("scope_id", sa.String(length=36), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("deactivated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_memberships_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memberships")),
        sa.UniqueConstraint(
            "user_id",
            "scope_kind",
            "scope_id",
            name=op.f("uq_memberships_user_id_scope_kind_scope_id"),
        ),
    )
    with op.batch_alter_table("memberships", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_memberships_scope_kind_scope_id"),
            ["scope_kind", "scope_id"],
            unique=False,
        )

    op.create_table(
        "provider_assignments",
        sa.Column("customer_id", sa.String(length=36), nullable=False),
        sa.Column("provider_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_provider_assignments_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["service_providers.id"],
            name=op.f("fk_provider_assignments_provider_id_service_providers"),
        ),
        sa.PrimaryKeyConstraint("customer_id", name=op.f("pk_provider_assignments")),
    )
    with op.batch_alter_table("provider_assignments", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_provider_assignments_provider_id"), ["provider_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("provider_assignments", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_provider_assignments_provider_id"))

    op.drop_table("provider_assignments")
    with op.batch_alter_table("memberships", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_memberships_scope_kind_scope_id"))

    op.drop_table("memberships")
    op.drop_table("customer_parameters")
    op.drop_table("users")
    op.drop_table("service_providers")
    with op.batch_alter_table("customers", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_customers_ico_status"))

    op.drop_table("customers")
