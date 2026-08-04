"""Separate amortized book carrying amount from acquisition/tax lot basis.

Revision ID: c144b2c3d511
Revises: c143b2c3d510
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c144b2c3d511"
down_revision: str | Sequence[str] | None = "c143b2c3d510"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "position_lot_state"
_SHAPE_CONSTRAINT = "ck_position_lot_amortized_cost_shape"
_VALUES_CONSTRAINT = "ck_position_lot_amortized_cost_values"
_CARRY_COLUMNS = (
    "amortized_book_carrying_local",
    "amortized_book_carrying_base",
)


def upgrade() -> None:
    """Add independent book carrying values and migrate existing complete carry rows."""

    _drop_carry_constraints()
    for column_name in _CARRY_COLUMNS:
        op.add_column(_TABLE, sa.Column(column_name, sa.Numeric(18, 10), nullable=True))
    _require_acquisition_basis_evidence()
    op.execute(
        "UPDATE position_lot_state AS lot "
        "SET amortized_book_carrying_local = lot.lot_cost_local, "
        "amortized_book_carrying_base = lot.lot_cost_base, "
        "lot_cost_local = CAST("
        "source.net_cost_local * lot.open_quantity / source.quantity AS NUMERIC(18, 10)), "
        "lot_cost_base = CAST("
        "source.net_cost * lot.open_quantity / source.quantity AS NUMERIC(18, 10)) "
        "FROM transactions AS source "
        "WHERE lot.amortized_cost_profile_id IS NOT NULL "
        "AND source.transaction_id = lot.source_transaction_id"
    )
    _create_carry_constraints(include_independent_amounts=True)


def downgrade() -> None:
    """Restore the c143 combined carry representation, then remove independent values."""

    _drop_carry_constraints()
    op.execute(
        "UPDATE position_lot_state "
        "SET lot_cost_local = amortized_book_carrying_local, "
        "lot_cost_base = amortized_book_carrying_base "
        "WHERE amortized_cost_profile_id IS NOT NULL"
    )
    for column_name in reversed(_CARRY_COLUMNS):
        op.drop_column(_TABLE, column_name)
    _create_carry_constraints(include_independent_amounts=False)


def _carry_columns(*, include_independent_amounts: bool) -> tuple[str, ...]:
    columns = (
        "amortized_cost_profile_id",
        "amortized_cost_profile_version",
        "amortized_cost_profile_content_hash",
        "amortized_cost_recognized_through",
        "amortized_cost_scheduled_local",
        "amortized_cost_book_fx_rate_to_base",
    )
    if include_independent_amounts:
        columns += _CARRY_COLUMNS
    return columns


def _drop_carry_constraints() -> None:
    for constraint_name in (_VALUES_CONSTRAINT, _SHAPE_CONSTRAINT):
        op.drop_constraint(constraint_name, _TABLE, type_="check")


def _require_acquisition_basis_evidence() -> None:
    """Fail closed unless every legacy carry row has exact FIFO acquisition evidence."""

    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS ("
        "SELECT 1 FROM position_lot_state AS lot "
        "LEFT JOIN transactions AS source "
        "ON source.transaction_id = lot.source_transaction_id "
        "WHERE lot.amortized_cost_profile_id IS NOT NULL "
        "AND (source.transaction_id IS NULL "
        "OR source.transaction_type <> 'BUY' "
        "OR source.quantity IS NULL OR source.quantity <= 0 "
        "OR source.net_cost_local IS NULL OR source.net_cost IS NULL "
        "OR source.net_cost_local < 0 OR source.net_cost < 0 "
        "OR lot.open_quantity > source.quantity)"
        ") THEN "
        "RAISE EXCEPTION "
        "'cannot separate amortized book carry without complete FIFO acquisition basis evidence'; "
        "END IF; END $$"
    )


def _create_carry_constraints(*, include_independent_amounts: bool) -> None:
    columns = _carry_columns(include_independent_amounts=include_independent_amounts)
    all_null = " AND ".join(f"{column} IS NULL" for column in columns)
    all_present = " AND ".join(f"{column} IS NOT NULL" for column in columns)
    op.create_check_constraint(
        _SHAPE_CONSTRAINT,
        _TABLE,
        f"({all_null}) OR ({all_present})",
    )
    value_terms = [
        "open_quantity > 0",
        "amortized_cost_profile_version >= 1",
        "amortized_cost_profile_id = btrim(amortized_cost_profile_id)",
        "amortized_cost_profile_id <> ''",
        "amortized_cost_profile_content_hash ~ '^[0-9a-f]{64}$'",
        "amortized_cost_recognized_through >= acquisition_date",
        "amortized_cost_scheduled_local >= 0",
        "amortized_cost_book_fx_rate_to_base > 0",
        "CAST(amortized_cost_scheduled_local AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
        "CAST(amortized_cost_book_fx_rate_to_base AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
    ]
    if include_independent_amounts:
        for column_name in _CARRY_COLUMNS:
            value_terms.extend(
                (
                    f"{column_name} >= 0",
                    f"CAST({column_name} AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
                )
            )
    op.create_check_constraint(
        _VALUES_CONSTRAINT,
        _TABLE,
        "amortized_cost_profile_id IS NULL OR (" + " AND ".join(value_terms) + ")",
    )
