"""Preserve the exact currency and FX facts used by position valuations.

Revision ID: c163b2c3d52a
Revises: c162b2c3d529
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c163b2c3d52a"
down_revision: str | Sequence[str] | None = "c162b2c3d529"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "daily_position_snapshots",
        sa.Column("valuation_source_currency", sa.String(length=3), nullable=True),
    )
    op.add_column(
        "daily_position_snapshots",
        sa.Column("valuation_reporting_currency", sa.String(length=3), nullable=True),
    )
    op.add_column(
        "daily_position_snapshots",
        sa.Column("valuation_fx_rate_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "daily_position_snapshots",
        sa.Column("valuation_fx_rate", sa.Numeric(18, 10), nullable=True),
    )
    op.create_check_constraint(
        "ck_daily_position_snapshot_valuation_fx_fact",
        "daily_position_snapshots",
        "(valuation_fx_rate_date IS NULL AND valuation_fx_rate IS NULL) OR "
        "(valuation_fx_rate_date IS NOT NULL "
        "AND valuation_fx_rate IS NOT NULL "
        "AND valuation_source_currency IS NOT NULL "
        "AND valuation_reporting_currency IS NOT NULL "
        "AND valuation_source_currency <> valuation_reporting_currency "
        "AND CAST(valuation_fx_rate AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity'))",
    )
    op.create_check_constraint(
        "ck_daily_snapshot_valuation_currency_pair",
        "daily_position_snapshots",
        "(valuation_source_currency IS NULL AND valuation_reporting_currency IS NULL) OR "
        "(valuation_source_currency IS NOT NULL AND valuation_reporting_currency IS NOT NULL "
        "AND valuation_source_currency = upper(btrim(valuation_source_currency)) "
        "AND valuation_reporting_currency = upper(btrim(valuation_reporting_currency)) "
        "AND char_length(valuation_source_currency) = 3 "
        "AND char_length(valuation_reporting_currency) = 3)",
    )
    op.create_check_constraint(
        "ck_daily_snapshot_fx_rate_positive",
        "daily_position_snapshots",
        "valuation_fx_rate > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_daily_snapshot_valuation_currency_pair",
        "daily_position_snapshots",
        type_="check",
    )
    op.drop_constraint(
        "ck_daily_snapshot_fx_rate_positive",
        "daily_position_snapshots",
        type_="check",
    )
    op.drop_constraint(
        "ck_daily_position_snapshot_valuation_fx_fact",
        "daily_position_snapshots",
        type_="check",
    )
    op.drop_column("daily_position_snapshots", "valuation_fx_rate")
    op.drop_column("daily_position_snapshots", "valuation_fx_rate_date")
    op.drop_column("daily_position_snapshots", "valuation_reporting_currency")
    op.drop_column("daily_position_snapshots", "valuation_source_currency")
