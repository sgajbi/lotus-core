"""Add governed reconciliation finding lifecycle evidence.

Revision ID: c132b2c3d505
Revises: c131b2c3d504
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c132b2c3d505"
down_revision: str | Sequence[str] | None = "c131b2c3d504"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "financial_reconciliation_findings"
_INDEX = "ix_fin_recon_findings_run_resolution_severity_created_id"
_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    ("ck_fin_recon_finding_owner_nonempty", "btrim(owner) <> ''"),
    (
        "ck_fin_recon_finding_resolution_state",
        "resolution_state IN ('OPEN', 'IN_PROGRESS', 'RESOLVED', 'WAIVED', 'SUPPRESSED')",
    ),
    (
        "ck_fin_recon_finding_resolution_evidence",
        "("
        "resolution_state IN ('OPEN', 'IN_PROGRESS') "
        "AND resolution_actor IS NULL AND resolved_at IS NULL"
        ") OR ("
        "resolution_state IN ('RESOLVED', 'WAIVED', 'SUPPRESSED') "
        "AND resolution_actor IS NOT NULL AND btrim(resolution_actor) <> '' "
        "AND resolved_at IS NOT NULL AND resolved_at >= created_at"
        ")",
    ),
    (
        "ck_fin_recon_finding_tolerance_finite",
        "CAST(tolerance AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    ("ck_fin_recon_finding_tolerance_nonnegative", "tolerance >= 0"),
    (
        "ck_fin_recon_finding_observed_delta_finite",
        "CAST(observed_delta AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    ("ck_fin_recon_finding_repair_nonempty", "btrim(repair_recommendation) <> ''"),
)


def _backfill_owner() -> None:
    op.execute(
        f"""
        UPDATE {_TABLE}
        SET owner = CASE lower(btrim(reconciliation_type))
            WHEN 'position_valuation' THEN 'VALUATION_OPERATIONS'
            WHEN 'timeseries_integrity' THEN 'PORTFOLIO_CONTROL_OPERATIONS'
            WHEN 'transaction_cashflow' THEN 'TRANSACTION_OPERATIONS'
            ELSE 'FINANCIAL_CONTROL_OPERATIONS'
        END
        WHERE owner IS NULL
        """
    )


def _backfill_repair_recommendation() -> None:
    op.execute(
        f"""
        UPDATE {_TABLE}
        SET repair_recommendation = CASE lower(btrim(finding_type))
            WHEN 'cashflow_rule_mismatch' THEN 'REBUILD_CASHFLOW_FROM_GOVERNED_RULE'
            WHEN 'invalid_market_price' THEN 'CORRECT_MARKET_PRICE_SOURCE'
            WHEN 'market_value_local_mismatch' THEN 'REVALUE_POSITION'
            WHEN 'missing_cashflow' THEN 'REGENERATE_CASHFLOW'
            WHEN 'missing_portfolio_timeseries' THEN 'REBUILD_DERIVED_TIMESERIES'
            WHEN 'missing_position_timeseries' THEN 'REBUILD_DERIVED_TIMESERIES'
            WHEN 'portfolio_timeseries_aggregate_mismatch' THEN 'REBUILD_PORTFOLIO_TIMESERIES'
            WHEN 'position_timeseries_completeness_gap' THEN 'REBUILD_DERIVED_TIMESERIES'
            WHEN 'unrealized_gain_loss_local_mismatch' THEN 'REVALUE_POSITION'
            WHEN 'unsupported_authoritative_valuation_receipt'
                THEN 'REBUILD_VALUATION_WITH_SUPPORTED_POLICY'
            ELSE 'REVIEW_RECONCILIATION_BREAK'
        END
        WHERE repair_recommendation IS NULL
        """
    )


def upgrade() -> None:
    """Backfill existing rows before enforcing the additive evidence contract."""

    op.add_column(_TABLE, sa.Column("owner", sa.String(length=100), nullable=True))
    op.add_column(
        _TABLE,
        sa.Column(
            "resolution_state",
            sa.String(length=20),
            nullable=False,
            server_default="OPEN",
        ),
    )
    op.add_column(_TABLE, sa.Column("resolution_actor", sa.String(length=200), nullable=True))
    op.add_column(_TABLE, sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(_TABLE, sa.Column("tolerance", sa.Numeric(18, 10), nullable=True))
    op.add_column(_TABLE, sa.Column("observed_delta", sa.Numeric(18, 10), nullable=True))
    op.add_column(
        _TABLE,
        sa.Column("repair_recommendation", sa.String(length=100), nullable=True),
    )
    _backfill_owner()
    _backfill_repair_recommendation()
    op.alter_column(_TABLE, "owner", existing_type=sa.String(length=100), nullable=False)
    op.alter_column(
        _TABLE,
        "repair_recommendation",
        existing_type=sa.String(length=100),
        nullable=False,
    )
    for name, condition in _CONSTRAINTS:
        op.create_check_constraint(
            name,
            _TABLE,
            condition,
            postgresql_not_valid=True,
        )
    op.execute(
        f'ALTER TABLE "{_TABLE}" '
        + ", ".join(f'VALIDATE CONSTRAINT "{name}"' for name, _ in _CONSTRAINTS)
    )
    op.create_index(
        _INDEX,
        _TABLE,
        ["run_id", "resolution_state", "severity", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(_INDEX, table_name=_TABLE)
    for name, _ in reversed(_CONSTRAINTS):
        op.drop_constraint(name, _TABLE, type_="check")
    for column_name in (
        "repair_recommendation",
        "observed_delta",
        "tolerance",
        "resolved_at",
        "resolution_actor",
        "resolution_state",
        "owner",
    ):
        op.drop_column(_TABLE, column_name)
