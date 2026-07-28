"""Enforce finite derived-timeseries and reconciliation numeric boundaries.

Revision ID: c126b2c3d4ff
Revises: c125b2c3d4fe
Create Date: 2026-07-28 18:40:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c126b2c3d4ff"
down_revision: str | Sequence[str] | None = "c125b2c3d4fe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINTS: tuple[tuple[str, str, str], ...] = (
    (
        "position_timeseries",
        "ck_position_timeseries_values_finite",
        "CAST(bod_market_value AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(bod_cashflow_position AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(eod_cashflow_position AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(bod_cashflow_portfolio AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(eod_cashflow_portfolio AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(eod_market_value AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(fees AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(quantity AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(cost AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    (
        "portfolio_timeseries",
        "ck_portfolio_timeseries_values_finite",
        "CAST(bod_market_value AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(bod_cashflow AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(eod_cashflow AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(eod_market_value AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(fees AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    (
        "financial_reconciliation_runs",
        "ck_fin_recon_tolerance_finite",
        "CAST(tolerance AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    (
        "financial_reconciliation_runs",
        "ck_fin_recon_tolerance_nonnegative",
        "tolerance >= 0",
    ),
)


def _validation_statements() -> tuple[str, ...]:
    grouped: dict[str, list[str]] = {}
    for table_name, constraint_name, _ in _CONSTRAINTS:
        grouped.setdefault(table_name, []).append(constraint_name)
    return tuple(
        f'ALTER TABLE "{table_name}" '
        + ", ".join(
            f'VALIDATE CONSTRAINT "{constraint_name}"' for constraint_name in constraint_names
        )
        for table_name, constraint_names in grouped.items()
    )


def upgrade() -> None:
    """Block new invalid writes before validating retained derived state."""

    for table_name, constraint_name, condition in _CONSTRAINTS:
        op.create_check_constraint(
            constraint_name,
            table_name,
            condition,
            postgresql_not_valid=True,
        )
    for statement in _validation_statements():
        op.execute(statement)


def downgrade() -> None:
    for table_name, constraint_name, _ in reversed(_CONSTRAINTS):
        op.drop_constraint(constraint_name, table_name, type_="check")
