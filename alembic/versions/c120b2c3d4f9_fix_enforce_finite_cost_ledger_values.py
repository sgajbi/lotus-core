"""Enforce finite, nonnegative cost-ledger persistence values.

Revision ID: c120b2c3d4f9
Revises: c119b2c3d4f8
Create Date: 2026-07-23 20:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c120b2c3d4f9"
down_revision: str | Sequence[str] | None = "c119b2c3d4f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINTS: tuple[tuple[str, str, str], ...] = (
    (
        "transactions",
        "ck_transactions_quantity_finite",
        "CAST(quantity AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    (
        "transactions",
        "ck_transactions_quantity_nonnegative",
        "quantity >= 0",
    ),
    (
        "transaction_costs",
        "ck_transaction_costs_amount_finite",
        "CAST(amount AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    (
        "position_lot_state",
        "ck_position_lot_state_numeric_finite",
        "CAST(original_quantity AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(open_quantity AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(lot_cost_local AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(lot_cost_base AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(accrued_interest_paid_local AS TEXT) "
        "NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    (
        "position_lot_state",
        "ck_position_lot_original_quantity_nonnegative",
        "original_quantity >= 0",
    ),
    (
        "position_lot_state",
        "ck_position_lot_accrued_interest_nonnegative",
        "accrued_interest_paid_local >= 0",
    ),
    (
        "cost_basis_processing_state",
        "ck_cost_basis_processing_quantity_finite",
        "CAST(latest_quantity AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    (
        "cost_basis_processing_state",
        "ck_cost_basis_processing_quantity_nonnegative",
        "latest_quantity >= 0",
    ),
    (
        "average_cost_pool_state",
        "ck_average_cost_pool_numeric_finite",
        "CAST(pool_quantity AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(pool_cost_local AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(pool_cost_base AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    (
        "accrued_income_offset_state",
        "ck_accrued_income_offset_numeric_finite",
        "CAST(accrued_interest_paid_local AS TEXT) "
        "NOT IN ('NaN', 'Infinity', '-Infinity') "
        "AND CAST(remaining_offset_local AS TEXT) "
        "NOT IN ('NaN', 'Infinity', '-Infinity')",
    ),
    (
        "accrued_income_offset_state",
        "ck_accrued_income_paid_nonnegative",
        "accrued_interest_paid_local >= 0",
    ),
    (
        "accrued_income_offset_state",
        "ck_accrued_income_remaining_nonnegative",
        "remaining_offset_local >= 0",
    ),
)

_VALIDATION_STATEMENTS: tuple[str, ...] = (
    'ALTER TABLE "transactions" '
    'VALIDATE CONSTRAINT "ck_transactions_quantity_finite", '
    'VALIDATE CONSTRAINT "ck_transactions_quantity_nonnegative"',
    'ALTER TABLE "transaction_costs" VALIDATE CONSTRAINT "ck_transaction_costs_amount_finite"',
    'ALTER TABLE "position_lot_state" '
    'VALIDATE CONSTRAINT "ck_position_lot_state_numeric_finite", '
    'VALIDATE CONSTRAINT "ck_position_lot_original_quantity_nonnegative", '
    'VALIDATE CONSTRAINT "ck_position_lot_accrued_interest_nonnegative"',
    'ALTER TABLE "cost_basis_processing_state" '
    'VALIDATE CONSTRAINT "ck_cost_basis_processing_quantity_finite", '
    'VALIDATE CONSTRAINT "ck_cost_basis_processing_quantity_nonnegative"',
    'ALTER TABLE "average_cost_pool_state" '
    'VALIDATE CONSTRAINT "ck_average_cost_pool_numeric_finite"',
    'ALTER TABLE "accrued_income_offset_state" '
    'VALIDATE CONSTRAINT "ck_accrued_income_offset_numeric_finite", '
    'VALIDATE CONSTRAINT "ck_accrued_income_paid_nonnegative", '
    'VALIDATE CONSTRAINT "ck_accrued_income_remaining_nonnegative"',
)


def upgrade() -> None:
    """Install without a table rewrite, then prove all retained rows comply."""

    for table_name, constraint_name, condition in _CONSTRAINTS:
        op.create_check_constraint(
            constraint_name,
            table_name,
            condition,
            postgresql_not_valid=True,
        )
    for statement in _VALIDATION_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for table_name, constraint_name, _ in reversed(_CONSTRAINTS):
        op.drop_constraint(constraint_name, table_name, type_="check")
