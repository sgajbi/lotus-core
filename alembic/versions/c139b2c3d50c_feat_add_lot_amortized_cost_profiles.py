"""Add immutable lot amortized-cost profile and period ledgers.

Revision ID: c139b2c3d50c
Revises: c138b2c3d50b
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c139b2c3d50c"
down_revision: str | Sequence[str] | None = "c138b2c3d50b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_portfolios_book_scope_identity",
        "portfolios",
        ["tenant_id", "legal_book_id", "portfolio_id"],
    )
    op.create_unique_constraint(
        "uq_position_lot_scope_identity",
        "position_lot_state",
        ["lot_id", "portfolio_id", "security_id"],
    )
    op.create_table(
        "lot_amortized_cost_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("profile_id", sa.String(length=96), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("legal_book_id", sa.String(), nullable=False),
        sa.Column("portfolio_id", sa.String(), nullable=False),
        sa.Column("security_id", sa.String(), nullable=False),
        sa.Column("lot_id", sa.String(), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("eligibility_reason", sa.String(), nullable=True),
        sa.Column("policy_id", sa.String(), nullable=True),
        sa.Column("policy_version", sa.Integer(), nullable=True),
        sa.Column("schedule_version", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("direction", sa.String(), nullable=True),
        sa.Column("initial_amortized_cost_local", sa.Numeric(18, 10), nullable=True),
        sa.Column("redemption_value_local", sa.Numeric(18, 10), nullable=True),
        sa.Column("final_amortized_cost_local", sa.Numeric(18, 10), nullable=True),
        sa.Column("residual_local", sa.Numeric(18, 10), nullable=True),
        sa.Column("authority_content_hash", sa.String(length=64), nullable=True),
        sa.Column("source_references", postgresql.JSONB(none_as_null=True), nullable=False),
        sa.Column("calculation_lineage", postgresql.JSONB(none_as_null=True), nullable=True),
        sa.Column("profile_content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "profile_version >= 1",
            name="ck_lot_amort_profile_version_positive",
        ),
        sa.CheckConstraint(
            "tenant_id = btrim(tenant_id) AND tenant_id <> '' "
            "AND legal_book_id = btrim(legal_book_id) AND legal_book_id <> '' "
            "AND portfolio_id = btrim(portfolio_id) AND portfolio_id <> '' "
            "AND security_id = btrim(security_id) AND security_id <> '' "
            "AND lot_id = btrim(lot_id) AND lot_id <> ''",
            name="ck_lot_amort_profile_scope_normalized",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'PARKED', 'INELIGIBLE')",
            name="ck_lot_amort_profile_status",
        ),
        sa.CheckConstraint(
            "direction IS NULL OR direction IN "
            "('PREMIUM_AMORTIZATION', 'DISCOUNT_ACCRETION', 'AT_PAR')",
            name="ck_lot_amort_profile_direction",
        ),
        sa.CheckConstraint(
            "currency IS NULL OR currency ~ '^[A-Z]{3}$'",
            name="ck_lot_amort_profile_currency",
        ),
        sa.CheckConstraint(
            "policy_version IS NULL OR policy_version >= 1",
            name="ck_lot_amort_profile_policy_version",
        ),
        sa.CheckConstraint(
            "schedule_version IS NULL OR schedule_version >= 1",
            name="ck_lot_amort_profile_schedule_version",
        ),
        sa.CheckConstraint(
            "CAST(initial_amortized_cost_local AS TEXT) "
            "NOT IN ('NaN', 'Infinity', '-Infinity') "
            "AND CAST(redemption_value_local AS TEXT) "
            "NOT IN ('NaN', 'Infinity', '-Infinity') "
            "AND CAST(final_amortized_cost_local AS TEXT) "
            "NOT IN ('NaN', 'Infinity', '-Infinity') "
            "AND CAST(residual_local AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
            name="ck_lot_amort_profile_amounts_finite",
        ),
        sa.CheckConstraint(
            "initial_amortized_cost_local >= 0",
            name="ck_lot_amort_profile_initial_nonnegative",
        ),
        sa.CheckConstraint(
            "redemption_value_local >= 0",
            name="ck_lot_amort_profile_redemption_nonnegative",
        ),
        sa.CheckConstraint(
            "final_amortized_cost_local >= 0",
            name="ck_lot_amort_profile_final_nonnegative",
        ),
        sa.CheckConstraint(
            "authority_content_hash IS NULL OR authority_content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_lot_amort_profile_authority_hash",
        ),
        sa.CheckConstraint(
            "profile_content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_lot_amort_profile_content_hash",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(source_references) = 'array'",
            name="ck_lot_amort_profile_sources_array",
        ),
        sa.CheckConstraint(
            "(status = 'ACTIVE' AND eligibility_reason IS NULL "
            "AND policy_id IS NOT NULL AND policy_version IS NOT NULL "
            "AND schedule_version IS NOT NULL AND currency IS NOT NULL "
            "AND direction IS NOT NULL AND initial_amortized_cost_local IS NOT NULL "
            "AND redemption_value_local IS NOT NULL "
            "AND final_amortized_cost_local IS NOT NULL AND residual_local IS NOT NULL "
            "AND authority_content_hash IS NOT NULL AND calculation_lineage IS NOT NULL "
            "AND jsonb_array_length(source_references) > 0) "
            "OR (status IN ('PARKED', 'INELIGIBLE') AND eligibility_reason IS NOT NULL "
            "AND direction IS NULL AND initial_amortized_cost_local IS NULL "
            "AND redemption_value_local IS NULL AND final_amortized_cost_local IS NULL "
            "AND residual_local IS NULL AND calculation_lineage IS NULL)",
            name="ck_lot_amort_profile_lifecycle_shape",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "legal_book_id", "portfolio_id"],
            ["portfolios.tenant_id", "portfolios.legal_book_id", "portfolios.portfolio_id"],
            name="fk_lot_amort_profile_book_scope",
        ),
        sa.ForeignKeyConstraint(
            ["security_id"],
            ["instruments.security_id"],
            name="fk_lot_amort_profile_security",
        ),
        sa.ForeignKeyConstraint(
            ["lot_id", "portfolio_id", "security_id"],
            [
                "position_lot_state.lot_id",
                "position_lot_state.portfolio_id",
                "position_lot_state.security_id",
            ],
            name="fk_lot_amort_profile_lot_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_lot_amortized_cost_profiles"),
        sa.UniqueConstraint(
            "profile_id",
            "profile_version",
            name="uq_lot_amort_profile_version",
        ),
    )
    op.create_index(
        "ix_lot_amort_profile_scope_version",
        "lot_amortized_cost_profiles",
        [
            "tenant_id",
            "legal_book_id",
            "portfolio_id",
            "security_id",
            "lot_id",
            sa.text("profile_version DESC"),
        ],
        unique=False,
    )
    op.create_index(
        "ix_lot_amort_profile_parked_effective",
        "lot_amortized_cost_profiles",
        ["status", "effective_date", "profile_id"],
        unique=False,
        postgresql_where=sa.text("status IN ('PARKED', 'INELIGIBLE')"),
    )
    op.create_index(
        "ix_lot_amort_profile_id_effective_version",
        "lot_amortized_cost_profiles",
        ["profile_id", sa.text("effective_date DESC"), sa.text("profile_version DESC")],
        unique=False,
    )

    op.create_table(
        "lot_amortized_cost_periods",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("profile_id", sa.String(length=96), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("period_ordinal", sa.Integer(), nullable=False),
        sa.Column("period_start_date", sa.Date(), nullable=False),
        sa.Column("period_end_date", sa.Date(), nullable=False),
        sa.Column("year_fraction", sa.Numeric(), nullable=False),
        sa.Column("period_rate", sa.Numeric(), nullable=True),
        sa.Column("begin_amortized_cost_local", sa.Numeric(18, 10), nullable=False),
        sa.Column("interest_income_local", sa.Numeric(18, 10), nullable=False),
        sa.Column("cash_coupon_local", sa.Numeric(18, 10), nullable=False),
        sa.Column("amortization_amount_local", sa.Numeric(18, 10), nullable=False),
        sa.Column("end_amortized_cost_local", sa.Numeric(18, 10), nullable=False),
        sa.Column("rounding_adjustment_local", sa.Numeric(18, 10), nullable=False),
        sa.Column("calculation_output_hash", sa.String(length=64), nullable=False),
        sa.Column("period_content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "profile_version >= 1 AND period_ordinal >= 1",
            name="ck_lot_amort_period_identity_positive",
        ),
        sa.CheckConstraint(
            "period_end_date > period_start_date",
            name="ck_lot_amort_period_date_order",
        ),
        sa.CheckConstraint(
            "CAST(year_fraction AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
            "AND CAST(period_rate AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
            "AND CAST(begin_amortized_cost_local AS TEXT) "
            "NOT IN ('NaN', 'Infinity', '-Infinity') "
            "AND CAST(interest_income_local AS TEXT) "
            "NOT IN ('NaN', 'Infinity', '-Infinity') "
            "AND CAST(cash_coupon_local AS TEXT) "
            "NOT IN ('NaN', 'Infinity', '-Infinity') "
            "AND CAST(amortization_amount_local AS TEXT) "
            "NOT IN ('NaN', 'Infinity', '-Infinity') "
            "AND CAST(end_amortized_cost_local AS TEXT) "
            "NOT IN ('NaN', 'Infinity', '-Infinity') "
            "AND CAST(rounding_adjustment_local AS TEXT) "
            "NOT IN ('NaN', 'Infinity', '-Infinity')",
            name="ck_lot_amort_period_amounts_finite",
        ),
        sa.CheckConstraint(
            "year_fraction > 0 AND begin_amortized_cost_local >= 0 "
            "AND cash_coupon_local >= 0 AND end_amortized_cost_local >= 0",
            name="ck_lot_amort_period_amounts_governed",
        ),
        sa.CheckConstraint(
            "calculation_output_hash ~ '^[0-9a-f]{64}$' AND period_content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_lot_amort_period_hashes",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id", "profile_version"],
            [
                "lot_amortized_cost_profiles.profile_id",
                "lot_amortized_cost_profiles.profile_version",
            ],
            name="fk_lot_amort_period_profile_version",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_lot_amortized_cost_periods"),
        sa.UniqueConstraint(
            "profile_id",
            "profile_version",
            "period_ordinal",
            name="uq_lot_amort_period_ordinal",
        ),
    )
    op.create_index(
        "ix_lot_amort_period_profile_end",
        "lot_amortized_cost_periods",
        ["profile_id", sa.text("profile_version DESC"), "period_end_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_lot_amort_period_profile_end",
        table_name="lot_amortized_cost_periods",
    )
    op.drop_table("lot_amortized_cost_periods")
    op.drop_index(
        "ix_lot_amort_profile_id_effective_version",
        table_name="lot_amortized_cost_profiles",
    )
    op.drop_index(
        "ix_lot_amort_profile_parked_effective",
        table_name="lot_amortized_cost_profiles",
    )
    op.drop_index(
        "ix_lot_amort_profile_scope_version",
        table_name="lot_amortized_cost_profiles",
    )
    op.drop_table("lot_amortized_cost_profiles")
    op.drop_constraint(
        "uq_position_lot_scope_identity",
        "position_lot_state",
        type_="unique",
    )
    op.drop_constraint(
        "uq_portfolios_book_scope_identity",
        "portfolios",
        type_="unique",
    )
