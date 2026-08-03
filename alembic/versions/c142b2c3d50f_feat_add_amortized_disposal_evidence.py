"""Add amortized carrying-amount evidence to lot-disposal allocations.

Revision ID: c142b2c3d50f
Revises: c141b2c3d50e
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c142b2c3d50f"
down_revision: str | Sequence[str] | None = "c141b2c3d50e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ALLOCATION_TABLE = "lot_disposal_allocations"
_PROFILE_TABLE = "lot_amortized_cost_profiles"


def upgrade() -> None:
    """Add an optional all-or-none evidence shape with a source-lot-safe profile reference."""

    op.create_unique_constraint(
        "uq_lot_amort_profile_allocation_scope",
        _PROFILE_TABLE,
        ["profile_id", "profile_version", "lot_id", "portfolio_id", "security_id"],
    )
    for column in _evidence_columns():
        op.add_column(_ALLOCATION_TABLE, column)
    op.create_check_constraint(
        "ck_lot_disposal_allocation_amort_shape",
        _ALLOCATION_TABLE,
        _evidence_shape_constraint(),
    )
    op.create_check_constraint(
        "ck_lot_disposal_allocation_amort_values",
        _ALLOCATION_TABLE,
        "(amortized_cost_profile_id IS NULL) OR ("
        "amortized_cost_profile_version >= 1 "
        "AND amortized_cost_profile_id = btrim(amortized_cost_profile_id) "
        "AND amortized_cost_profile_id <> '' "
        "AND amortized_cost_profile_content_hash ~ '^[0-9a-f]{64}$' "
        "AND amortized_cost_currency ~ '^[A-Z]{3}$' "
        "AND amortized_cost_original_quantity > 0 "
        "AND amortized_cost_open_quantity_before > 0 "
        "AND amortized_cost_open_quantity_before <= amortized_cost_original_quantity "
        "AND amortized_cost_residual_quantity >= 0 "
        "AND amortized_cost_current_local >= 0 "
        "AND amortized_cost_residual_local >= 0 "
        "AND amortized_cost_fx_rate_to_base > 0 "
        "AND amortized_cost_residual_base >= 0 "
        "AND jsonb_typeof(amortized_cost_calculation_lineage) = 'object')",
    )
    op.create_check_constraint(
        "ck_lot_disposal_allocation_amort_finite",
        _ALLOCATION_TABLE,
        "(amortized_cost_profile_id IS NULL) OR ("
        "CAST(amortized_cost_original_quantity AS TEXT) "
        "NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(amortized_cost_open_quantity_before AS TEXT) "
        "NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(amortized_cost_residual_quantity AS TEXT) "
        "NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(amortized_cost_current_local AS TEXT) "
        "NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(amortized_cost_residual_local AS TEXT) "
        "NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(amortized_cost_fx_rate_to_base AS TEXT) "
        "NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(amortized_cost_residual_base AS TEXT) "
        "NOT IN ('NaN', 'Infinity', '-Infinity'))",
    )
    op.create_foreign_key(
        "fk_lot_disposal_allocation_amort_profile",
        _ALLOCATION_TABLE,
        _PROFILE_TABLE,
        [
            "amortized_cost_profile_id",
            "amortized_cost_profile_version",
            "source_lot_id",
            "portfolio_id",
            "security_id",
        ],
        ["profile_id", "profile_version", "lot_id", "portfolio_id", "security_id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    """Remove the optional evidence reference before its profile uniqueness support."""

    op.drop_constraint(
        "fk_lot_disposal_allocation_amort_profile",
        _ALLOCATION_TABLE,
        type_="foreignkey",
    )
    for constraint_name in (
        "ck_lot_disposal_allocation_amort_finite",
        "ck_lot_disposal_allocation_amort_values",
        "ck_lot_disposal_allocation_amort_shape",
    ):
        op.drop_constraint(constraint_name, _ALLOCATION_TABLE, type_="check")
    for column in reversed(_evidence_columns()):
        op.drop_column(_ALLOCATION_TABLE, column.name)
    op.drop_constraint(
        "uq_lot_amort_profile_allocation_scope",
        _PROFILE_TABLE,
        type_="unique",
    )


def _evidence_columns() -> tuple[sa.Column[object], ...]:
    return (
        sa.Column("amortized_cost_profile_id", sa.String(length=96), nullable=True),
        sa.Column("amortized_cost_profile_version", sa.Integer(), nullable=True),
        sa.Column("amortized_cost_profile_content_hash", sa.String(length=64), nullable=True),
        sa.Column("amortized_cost_currency", sa.String(length=3), nullable=True),
        sa.Column("amortized_cost_recognized_through", sa.Date(), nullable=True),
        sa.Column("amortized_cost_original_quantity", sa.Numeric(18, 10), nullable=True),
        sa.Column("amortized_cost_open_quantity_before", sa.Numeric(18, 10), nullable=True),
        sa.Column("amortized_cost_residual_quantity", sa.Numeric(18, 10), nullable=True),
        sa.Column("amortized_cost_current_local", sa.Numeric(18, 10), nullable=True),
        sa.Column("amortized_cost_residual_local", sa.Numeric(18, 10), nullable=True),
        sa.Column("amortized_cost_fx_rate_to_base", sa.Numeric(18, 10), nullable=True),
        sa.Column("amortized_cost_residual_base", sa.Numeric(18, 10), nullable=True),
        sa.Column(
            "amortized_cost_calculation_lineage",
            postgresql.JSONB(none_as_null=True),
            nullable=True,
        ),
    )


def _evidence_shape_constraint() -> str:
    columns = tuple(column.name for column in _evidence_columns())
    all_null = " AND ".join(f"{column} IS NULL" for column in columns)
    all_present = " AND ".join(f"{column} IS NOT NULL" for column in columns)
    return f"({all_null}) OR ({all_present})"
