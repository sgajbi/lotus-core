"""add client tax source products

Revision ID: 5e6f7a8b9c0d
Revises: 4d5e6f7a8b9c
Create Date: 2026-05-14 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5e6f7a8b9c0d"
down_revision: str | None = "4d5e6f7a8b9c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "client_tax_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("client_id", sa.String(), nullable=False),
        sa.Column("portfolio_id", sa.String(), nullable=False),
        sa.Column("mandate_id", sa.String(), nullable=True),
        sa.Column("tax_profile_id", sa.String(), nullable=False),
        sa.Column("tax_residency_country", sa.String(), nullable=False),
        sa.Column("booking_tax_jurisdiction", sa.String(), nullable=False),
        sa.Column("tax_status", sa.String(), nullable=False),
        sa.Column("profile_status", sa.String(), server_default="active", nullable=False),
        sa.Column("withholding_tax_rate", sa.Numeric(18, 10), nullable=True),
        sa.Column(
            "capital_gains_tax_applicable", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column("income_tax_applicable", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("treaty_codes", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("eligible_account_types", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("profile_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("source_system", sa.String(), nullable=True),
        sa.Column("source_record_id", sa.String(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quality_status", sa.String(), server_default="accepted", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.portfolio_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "client_id",
            "portfolio_id",
            "tax_profile_id",
            "effective_from",
            "profile_version",
            name="_client_tax_profile_effective_uc",
        ),
    )
    op.create_index("ix_client_tax_profiles_client_id", "client_tax_profiles", ["client_id"])
    op.create_index("ix_client_tax_profiles_portfolio_id", "client_tax_profiles", ["portfolio_id"])
    op.create_index("ix_client_tax_profiles_mandate_id", "client_tax_profiles", ["mandate_id"])
    op.create_index(
        "ix_client_tax_profiles_tax_profile_id", "client_tax_profiles", ["tax_profile_id"]
    )
    op.create_index(
        "ix_client_tax_profiles_tax_residency_country",
        "client_tax_profiles",
        ["tax_residency_country"],
    )
    op.create_index(
        "ix_client_tax_profiles_booking_tax_jurisdiction",
        "client_tax_profiles",
        ["booking_tax_jurisdiction"],
    )
    op.create_index("ix_client_tax_profiles_tax_status", "client_tax_profiles", ["tax_status"])
    op.create_index(
        "ix_client_tax_profiles_profile_status", "client_tax_profiles", ["profile_status"]
    )
    op.create_index(
        "ix_client_tax_profiles_effective_from", "client_tax_profiles", ["effective_from"]
    )
    op.create_index("ix_client_tax_profiles_effective_to", "client_tax_profiles", ["effective_to"])
    op.create_index(
        "ix_client_tax_profiles_quality_status", "client_tax_profiles", ["quality_status"]
    )
    op.create_index(
        "ix_client_tax_profile_effective_window",
        "client_tax_profiles",
        ["portfolio_id", "client_id", "effective_from", "effective_to"],
    )

    op.create_table(
        "client_tax_rule_sets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("client_id", sa.String(), nullable=False),
        sa.Column("portfolio_id", sa.String(), nullable=False),
        sa.Column("mandate_id", sa.String(), nullable=True),
        sa.Column("rule_set_id", sa.String(), nullable=False),
        sa.Column("tax_year", sa.Integer(), nullable=False),
        sa.Column("jurisdiction_code", sa.String(), nullable=False),
        sa.Column("rule_code", sa.String(), nullable=False),
        sa.Column("rule_category", sa.String(), nullable=False),
        sa.Column("rule_status", sa.String(), nullable=False),
        sa.Column("rule_source", sa.String(), nullable=False),
        sa.Column("applies_to_asset_classes", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("applies_to_security_ids", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("applies_to_income_types", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("rate", sa.Numeric(18, 10), nullable=True),
        sa.Column("threshold_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("threshold_currency", sa.String(), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("rule_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("source_system", sa.String(), nullable=True),
        sa.Column("source_record_id", sa.String(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quality_status", sa.String(), server_default="accepted", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.portfolio_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "client_id",
            "portfolio_id",
            "rule_set_id",
            "jurisdiction_code",
            "rule_code",
            "effective_from",
            "rule_version",
            name="_client_tax_rule_set_effective_uc",
        ),
    )
    op.create_index("ix_client_tax_rule_sets_client_id", "client_tax_rule_sets", ["client_id"])
    op.create_index(
        "ix_client_tax_rule_sets_portfolio_id", "client_tax_rule_sets", ["portfolio_id"]
    )
    op.create_index("ix_client_tax_rule_sets_mandate_id", "client_tax_rule_sets", ["mandate_id"])
    op.create_index("ix_client_tax_rule_sets_rule_set_id", "client_tax_rule_sets", ["rule_set_id"])
    op.create_index("ix_client_tax_rule_sets_tax_year", "client_tax_rule_sets", ["tax_year"])
    op.create_index(
        "ix_client_tax_rule_sets_jurisdiction_code",
        "client_tax_rule_sets",
        ["jurisdiction_code"],
    )
    op.create_index("ix_client_tax_rule_sets_rule_code", "client_tax_rule_sets", ["rule_code"])
    op.create_index(
        "ix_client_tax_rule_sets_rule_category", "client_tax_rule_sets", ["rule_category"]
    )
    op.create_index("ix_client_tax_rule_sets_rule_status", "client_tax_rule_sets", ["rule_status"])
    op.create_index(
        "ix_client_tax_rule_sets_effective_from", "client_tax_rule_sets", ["effective_from"]
    )
    op.create_index(
        "ix_client_tax_rule_sets_effective_to", "client_tax_rule_sets", ["effective_to"]
    )
    op.create_index(
        "ix_client_tax_rule_sets_quality_status", "client_tax_rule_sets", ["quality_status"]
    )
    op.create_index(
        "ix_client_tax_rule_set_effective_window",
        "client_tax_rule_sets",
        ["portfolio_id", "client_id", "effective_from", "effective_to"],
    )


def downgrade() -> None:
    op.drop_index("ix_client_tax_rule_set_effective_window", table_name="client_tax_rule_sets")
    op.drop_index("ix_client_tax_rule_sets_quality_status", table_name="client_tax_rule_sets")
    op.drop_index("ix_client_tax_rule_sets_effective_to", table_name="client_tax_rule_sets")
    op.drop_index("ix_client_tax_rule_sets_effective_from", table_name="client_tax_rule_sets")
    op.drop_index("ix_client_tax_rule_sets_rule_status", table_name="client_tax_rule_sets")
    op.drop_index("ix_client_tax_rule_sets_rule_category", table_name="client_tax_rule_sets")
    op.drop_index("ix_client_tax_rule_sets_rule_code", table_name="client_tax_rule_sets")
    op.drop_index("ix_client_tax_rule_sets_jurisdiction_code", table_name="client_tax_rule_sets")
    op.drop_index("ix_client_tax_rule_sets_tax_year", table_name="client_tax_rule_sets")
    op.drop_index("ix_client_tax_rule_sets_rule_set_id", table_name="client_tax_rule_sets")
    op.drop_index("ix_client_tax_rule_sets_mandate_id", table_name="client_tax_rule_sets")
    op.drop_index("ix_client_tax_rule_sets_portfolio_id", table_name="client_tax_rule_sets")
    op.drop_index("ix_client_tax_rule_sets_client_id", table_name="client_tax_rule_sets")
    op.drop_table("client_tax_rule_sets")

    op.drop_index("ix_client_tax_profile_effective_window", table_name="client_tax_profiles")
    op.drop_index("ix_client_tax_profiles_quality_status", table_name="client_tax_profiles")
    op.drop_index("ix_client_tax_profiles_effective_to", table_name="client_tax_profiles")
    op.drop_index("ix_client_tax_profiles_effective_from", table_name="client_tax_profiles")
    op.drop_index("ix_client_tax_profiles_tax_status", table_name="client_tax_profiles")
    op.drop_index("ix_client_tax_profiles_profile_status", table_name="client_tax_profiles")
    op.drop_index(
        "ix_client_tax_profiles_booking_tax_jurisdiction", table_name="client_tax_profiles"
    )
    op.drop_index("ix_client_tax_profiles_tax_residency_country", table_name="client_tax_profiles")
    op.drop_index("ix_client_tax_profiles_tax_profile_id", table_name="client_tax_profiles")
    op.drop_index("ix_client_tax_profiles_mandate_id", table_name="client_tax_profiles")
    op.drop_index("ix_client_tax_profiles_portfolio_id", table_name="client_tax_profiles")
    op.drop_index("ix_client_tax_profiles_client_id", table_name="client_tax_profiles")
    op.drop_table("client_tax_profiles")
