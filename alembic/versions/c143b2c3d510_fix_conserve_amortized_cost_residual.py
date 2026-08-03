"""Conserve amortized-cost residual state across partial disposals.

Revision ID: c143b2c3d510
Revises: c142b2c3d50f
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c143b2c3d510"
down_revision: str | Sequence[str] | None = "c142b2c3d50f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LOT_TABLE = "position_lot_state"
_ALLOCATION_TABLE = "lot_disposal_allocations"
_PROFILE_TABLE = "lot_amortized_cost_profiles"


def upgrade() -> None:
    """Add exact open-lot carry state and complete allocation conservation evidence."""

    for column in _lot_carry_columns():
        op.add_column(_LOT_TABLE, column)
    op.create_check_constraint(
        "ck_position_lot_amortized_cost_shape",
        _LOT_TABLE,
        _all_or_none(column.name for column in _lot_carry_columns()),
    )
    op.create_check_constraint(
        "ck_position_lot_amortized_cost_values",
        _LOT_TABLE,
        "amortized_cost_profile_id IS NULL OR ("
        "open_quantity > 0 "
        "AND amortized_cost_profile_version >= 1 "
        "AND amortized_cost_profile_id = btrim(amortized_cost_profile_id) "
        "AND amortized_cost_profile_id <> '' "
        "AND amortized_cost_profile_content_hash ~ '^[0-9a-f]{64}$' "
        "AND amortized_cost_recognized_through >= acquisition_date "
        "AND amortized_cost_scheduled_local >= 0 "
        "AND amortized_cost_book_fx_rate_to_base > 0 "
        "AND CAST(amortized_cost_scheduled_local AS TEXT) "
        "NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(amortized_cost_book_fx_rate_to_base AS TEXT) "
        "NOT IN ('NaN', 'Infinity', '-Infinity'))",
    )
    op.create_foreign_key(
        "fk_position_lot_amortized_cost_profile",
        _LOT_TABLE,
        _PROFILE_TABLE,
        [
            "amortized_cost_profile_id",
            "amortized_cost_profile_version",
            "lot_id",
            "portfolio_id",
            "security_id",
        ],
        ["profile_id", "profile_version", "lot_id", "portfolio_id", "security_id"],
        ondelete="RESTRICT",
    )

    _drop_allocation_evidence_constraints()
    for column in _allocation_conservation_columns():
        op.add_column(_ALLOCATION_TABLE, column)
    _create_allocation_evidence_constraints(include_conservation=True)


def downgrade() -> None:
    """Restore the pre-carry evidence shape without discarding legacy allocation fields."""

    _drop_allocation_evidence_constraints()
    for column in reversed(_allocation_conservation_columns()):
        op.drop_column(_ALLOCATION_TABLE, column.name)
    _create_allocation_evidence_constraints(include_conservation=False)

    op.drop_constraint(
        "fk_position_lot_amortized_cost_profile",
        _LOT_TABLE,
        type_="foreignkey",
    )
    for constraint_name in (
        "ck_position_lot_amortized_cost_values",
        "ck_position_lot_amortized_cost_shape",
    ):
        op.drop_constraint(constraint_name, _LOT_TABLE, type_="check")
    for column in reversed(_lot_carry_columns()):
        op.drop_column(_LOT_TABLE, column.name)


def _lot_carry_columns() -> tuple[sa.Column[object], ...]:
    return (
        sa.Column("amortized_cost_profile_id", sa.String(length=96), nullable=True),
        sa.Column("amortized_cost_profile_version", sa.Integer(), nullable=True),
        sa.Column("amortized_cost_profile_content_hash", sa.String(length=64), nullable=True),
        sa.Column("amortized_cost_recognized_through", sa.Date(), nullable=True),
        sa.Column("amortized_cost_scheduled_local", sa.Numeric(18, 10), nullable=True),
        sa.Column("amortized_cost_book_fx_rate_to_base", sa.Numeric(18, 10), nullable=True),
    )


def _allocation_conservation_columns() -> tuple[sa.Column[object], ...]:
    return (
        sa.Column("amortized_cost_scheduled_local", sa.Numeric(18, 10), nullable=True),
        sa.Column("amortized_cost_current_base", sa.Numeric(18, 10), nullable=True),
        sa.Column("amortized_cost_retained_rounding_local", sa.Numeric(18, 10), nullable=True),
        sa.Column("amortized_cost_retained_rounding_base", sa.Numeric(18, 10), nullable=True),
    )


def _existing_allocation_evidence_columns() -> tuple[str, ...]:
    return (
        "amortized_cost_profile_id",
        "amortized_cost_profile_version",
        "amortized_cost_profile_content_hash",
        "amortized_cost_currency",
        "amortized_cost_recognized_through",
        "amortized_cost_original_quantity",
        "amortized_cost_open_quantity_before",
        "amortized_cost_residual_quantity",
        "amortized_cost_current_local",
        "amortized_cost_residual_local",
        "amortized_cost_book_fx_rate_to_base",
        "amortized_cost_residual_base",
        "amortized_cost_calculation_lineage",
    )


def _allocation_evidence_columns(*, include_conservation: bool) -> tuple[str, ...]:
    columns = _existing_allocation_evidence_columns()
    if include_conservation:
        columns += tuple(column.name for column in _allocation_conservation_columns())
    return columns


def _drop_allocation_evidence_constraints() -> None:
    for constraint_name in (
        "ck_lot_disposal_allocation_amort_finite",
        "ck_lot_disposal_allocation_amort_values",
        "ck_lot_disposal_allocation_amort_shape",
    ):
        op.drop_constraint(constraint_name, _ALLOCATION_TABLE, type_="check")


def _create_allocation_evidence_constraints(*, include_conservation: bool) -> None:
    columns = _allocation_evidence_columns(include_conservation=include_conservation)
    op.create_check_constraint(
        "ck_lot_disposal_allocation_amort_shape",
        _ALLOCATION_TABLE,
        _all_or_none(columns),
    )
    value_terms = [
        "amortized_cost_profile_version >= 1",
        "amortized_cost_profile_id = btrim(amortized_cost_profile_id)",
        "amortized_cost_profile_id <> ''",
        "amortized_cost_profile_content_hash ~ '^[0-9a-f]{64}$'",
        "amortized_cost_currency ~ '^[A-Z]{3}$'",
        "amortized_cost_original_quantity > 0",
        "amortized_cost_open_quantity_before > 0",
        "amortized_cost_open_quantity_before <= amortized_cost_original_quantity",
        "amortized_cost_residual_quantity >= 0",
        "amortized_cost_current_local >= 0",
        "amortized_cost_residual_local >= 0",
        "amortized_cost_book_fx_rate_to_base > 0",
        "amortized_cost_residual_base >= 0",
        "jsonb_typeof(amortized_cost_calculation_lineage) = 'object'",
    ]
    if include_conservation:
        value_terms.extend(
            (
                "amortized_cost_scheduled_local >= 0",
                "amortized_cost_current_base >= 0",
            )
        )
    op.create_check_constraint(
        "ck_lot_disposal_allocation_amort_values",
        _ALLOCATION_TABLE,
        "amortized_cost_profile_id IS NULL OR (" + " AND ".join(value_terms) + ")",
    )
    numeric_columns = [
        "amortized_cost_original_quantity",
        "amortized_cost_open_quantity_before",
        "amortized_cost_residual_quantity",
        "amortized_cost_current_local",
        "amortized_cost_residual_local",
        "amortized_cost_book_fx_rate_to_base",
        "amortized_cost_residual_base",
    ]
    if include_conservation:
        numeric_columns.extend(column.name for column in _allocation_conservation_columns())
    finite = " AND ".join(
        f"CAST({column} AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')"
        for column in numeric_columns
    )
    op.create_check_constraint(
        "ck_lot_disposal_allocation_amort_finite",
        _ALLOCATION_TABLE,
        f"amortized_cost_profile_id IS NULL OR ({finite})",
    )


def _all_or_none(columns: Sequence[str]) -> str:
    all_null = " AND ".join(f"{column} IS NULL" for column in columns)
    all_present = " AND ".join(f"{column} IS NOT NULL" for column in columns)
    return f"({all_null}) OR ({all_present})"
