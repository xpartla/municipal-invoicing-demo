"""codelists: versions and typed entries

Revision ID: 2280234ea511
Revises: 7f98fc09de45
Create Date: 2026-11-08 22:00:50.600120
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2280234ea511"
down_revision: str | Sequence[str] | None = "7f98fc09de45"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "codelist_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("customer_id", sa.String(length=36), nullable=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("entry_count", sa.Integer(), nullable=False),
        sa.Column("period", sa.String(length=7), nullable=True),
        sa.Column("source_name", sa.String(length=255), nullable=True),
        sa.Column("source_sha256", sa.String(length=64), nullable=True),
        sa.Column("source_rows", sa.Integer(), nullable=True),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("import_run_id", sa.String(length=36), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_codelist_versions_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_codelist_versions")),
        sa.UniqueConstraint(
            "customer_id",
            "kind",
            "year",
            "number",
            name=op.f("uq_codelist_versions_customer_id_kind_year_number"),
        ),
    )
    with op.batch_alter_table("codelist_versions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_codelist_versions_kind_year_status"),
            ["kind", "year", "status"],
            unique=False,
        )

    op.create_table(
        "accounts",
        sa.Column("su", sa.String(length=3), nullable=False),
        sa.Column("au", sa.String(length=3), nullable=False),
        sa.Column("type", sa.String(length=10), nullable=False),
        sa.Column("activity", sa.String(length=500), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("row", sa.Integer(), nullable=True),
        sa.Column("customer_id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("entry_key", sa.String(length=80), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_accounts_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["codelist_versions.id"],
            name=op.f("fk_accounts_version_id_codelist_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("version_id", "position", name=op.f("pk_accounts")),
        sa.UniqueConstraint(
            "version_id", "entry_key", name=op.f("uq_accounts_version_id_entry_key")
        ),
    )
    with op.batch_alter_table("accounts", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_accounts_customer_id_version_id"),
            ["customer_id", "version_id"],
            unique=False,
        )

    op.create_table(
        "budget_positions",
        sa.Column("direction", sa.String(length=7), nullable=False),
        sa.Column("ek", sa.String(length=6), nullable=False),
        sa.Column("zdroj", sa.String(length=4), nullable=False),
        sa.Column("oddiel", sa.String(length=2), nullable=True),
        sa.Column("trieda", sa.String(length=3), nullable=True),
        sa.Column("analytika", sa.String(length=3), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("rows", sa.JSON(), nullable=False),
        sa.Column("approved_cents", sa.BigInteger(), nullable=True),
        sa.Column("adjusted_cents", sa.BigInteger(), nullable=True),
        sa.Column("customer_id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("entry_key", sa.String(length=80), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_budget_positions_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["codelist_versions.id"],
            name=op.f("fk_budget_positions_version_id_codelist_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("version_id", "position", name=op.f("pk_budget_positions")),
        sa.UniqueConstraint(
            "version_id", "entry_key", name=op.f("uq_budget_positions_version_id_entry_key")
        ),
    )
    with op.batch_alter_table("budget_positions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_budget_positions_customer_id_ek"), ["customer_id", "ek"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_budget_positions_customer_id_version_id"),
            ["customer_id", "version_id"],
            unique=False,
        )

    op.create_table(
        "cofog_functions",
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("entry_key", sa.String(length=80), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["codelist_versions.id"],
            name=op.f("fk_cofog_functions_version_id_codelist_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("version_id", "position", name=op.f("pk_cofog_functions")),
        sa.UniqueConstraint(
            "version_id", "entry_key", name=op.f("uq_cofog_functions_version_id_entry_key")
        ),
    )
    op.create_table(
        "cost_centres",
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("customer_id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("entry_key", sa.String(length=80), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_cost_centres_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["codelist_versions.id"],
            name=op.f("fk_cost_centres_version_id_codelist_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("version_id", "position", name=op.f("pk_cost_centres")),
        sa.UniqueConstraint(
            "version_id", "entry_key", name=op.f("uq_cost_centres_version_id_entry_key")
        ),
    )
    with op.batch_alter_table("cost_centres", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_cost_centres_customer_id_version_id"),
            ["customer_id", "version_id"],
            unique=False,
        )

    op.create_table(
        "document_series",
        sa.Column("series_id", sa.String(length=50), nullable=False),
        sa.Column("pattern", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("bank_account", sa.String(length=200), nullable=True),
        sa.Column("customer_id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("entry_key", sa.String(length=80), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_document_series_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["codelist_versions.id"],
            name=op.f("fk_document_series_version_id_codelist_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("version_id", "position", name=op.f("pk_document_series")),
        sa.UniqueConstraint(
            "version_id", "entry_key", name=op.f("uq_document_series_version_id_entry_key")
        ),
    )
    with op.batch_alter_table("document_series", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_document_series_customer_id_version_id"),
            ["customer_id", "version_id"],
            unique=False,
        )

    op.create_table(
        "ek_codes",
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("entry_key", sa.String(length=80), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["codelist_versions.id"],
            name=op.f("fk_ek_codes_version_id_codelist_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("version_id", "position", name=op.f("pk_ek_codes")),
        sa.UniqueConstraint(
            "version_id", "entry_key", name=op.f("uq_ek_codes_version_id_entry_key")
        ),
    )
    op.create_table(
        "framework_accounts",
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("entry_key", sa.String(length=80), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["codelist_versions.id"],
            name=op.f("fk_framework_accounts_version_id_codelist_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("version_id", "position", name=op.f("pk_framework_accounts")),
        sa.UniqueConstraint(
            "version_id", "entry_key", name=op.f("uq_framework_accounts_version_id_entry_key")
        ),
    )
    op.create_table(
        "funding_sources",
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("entry_key", sa.String(length=80), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["codelist_versions.id"],
            name=op.f("fk_funding_sources_version_id_codelist_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("version_id", "position", name=op.f("pk_funding_sources")),
        sa.UniqueConstraint(
            "version_id", "entry_key", name=op.f("uq_funding_sources_version_id_entry_key")
        ),
    )
    op.create_table(
        "transfers",
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("zdroj", sa.String(length=4), nullable=False),
        sa.Column("mock", sa.Boolean(), nullable=False),
        sa.Column("customer_id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("entry_key", sa.String(length=80), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_transfers_customer_id_customers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["codelist_versions.id"],
            name=op.f("fk_transfers_version_id_codelist_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("version_id", "position", name=op.f("pk_transfers")),
        sa.UniqueConstraint(
            "version_id", "entry_key", name=op.f("uq_transfers_version_id_entry_key")
        ),
    )
    with op.batch_alter_table("transfers", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_transfers_customer_id_version_id"),
            ["customer_id", "version_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("transfers", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_transfers_customer_id_version_id"))

    op.drop_table("transfers")
    op.drop_table("funding_sources")
    op.drop_table("framework_accounts")
    op.drop_table("ek_codes")
    with op.batch_alter_table("document_series", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_document_series_customer_id_version_id"))

    op.drop_table("document_series")
    with op.batch_alter_table("cost_centres", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_cost_centres_customer_id_version_id"))

    op.drop_table("cost_centres")
    op.drop_table("cofog_functions")
    with op.batch_alter_table("budget_positions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_budget_positions_customer_id_version_id"))
        batch_op.drop_index(batch_op.f("ix_budget_positions_customer_id_ek"))

    op.drop_table("budget_positions")
    with op.batch_alter_table("accounts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_accounts_customer_id_version_id"))

    op.drop_table("accounts")
    with op.batch_alter_table("codelist_versions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_codelist_versions_kind_year_status"))

    op.drop_table("codelist_versions")
