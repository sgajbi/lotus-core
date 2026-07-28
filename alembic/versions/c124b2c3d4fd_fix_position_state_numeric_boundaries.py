"""Enforce finite simulation, position, and valuation-state numeric boundaries.

Revision ID: c124b2c3d4fd
Revises: c123b2c3d4fc
Create Date: 2026-07-28 18:20:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c124b2c3d4fd"
down_revision: str | Sequence[str] | None = "c123b2c3d4fc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINTS: tuple[tuple[str, str, str], ...] = (
    (
        "simulation_changes",
        "ck_simulation_change_values_finite",
        "CAST(quantity AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(price AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(amount AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    (
        "simulation_changes",
        "ck_simulation_change_price_positive",
        "price > 0",
    ),
    (
        "position_history",
        "ck_position_history_values_finite",
        "CAST(quantity AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(cost_basis AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(cost_basis_local AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    (
        "daily_position_snapshots",
        "ck_daily_position_snapshot_values_finite",
        "CAST(quantity AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(cost_basis AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(cost_basis_local AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(market_price AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(market_value AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(market_value_local AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(unrealized_gain_loss AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(unrealized_gain_loss_local AS TEXT) "
        "NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(unrealized_price_gain_loss AS TEXT) "
        "NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(unrealized_fx_gain_loss AS TEXT) "
        "NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    (
        "daily_position_snapshots",
        "ck_daily_position_snapshot_price_positive",
        "market_price > 0",
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
    """Block new invalid writes before validating retained position state."""

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
