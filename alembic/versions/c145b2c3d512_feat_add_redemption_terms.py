"""Add canonical fixed-income redemption terms to the transaction ledger.

Revision ID: c145b2c3d512
Revises: c144b2c3d511
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c145b2c3d512"
down_revision: str | Sequence[str] | None = "c144b2c3d511"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "transactions"
_NUMERIC_COLUMNS = (
    "old_factor",
    "new_factor",
    "principal_proceeds_local",
    "accrued_interest_proceeds_local",
    "embedded_fee_amount_local",
    "embedded_tax_amount_local",
)
_CONSTRAINTS = (
    "ck_transactions_redemption_values_finite",
    "ck_transactions_redemption_factor_transition",
    "ck_transactions_redemption_amounts_nonnegative",
)


def upgrade() -> None:
    """Add nullable source terms without changing existing transaction semantics."""

    op.add_column(_TABLE, sa.Column("redemption_price_type", sa.String(), nullable=True))
    for column_name in _NUMERIC_COLUMNS:
        op.add_column(_TABLE, sa.Column(column_name, sa.Numeric(18, 10), nullable=True))
    op.create_check_constraint(
        _CONSTRAINTS[0],
        _TABLE,
        " AND ".join(
            f"CAST({column} AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')"
            for column in _NUMERIC_COLUMNS
        ),
    )
    op.create_check_constraint(
        _CONSTRAINTS[1],
        _TABLE,
        "(old_factor IS NULL AND new_factor IS NULL) OR "
        "(old_factor IS NOT NULL AND new_factor IS NOT NULL "
        "AND old_factor > 0 AND new_factor >= 0 AND new_factor < old_factor)",
    )
    op.create_check_constraint(
        _CONSTRAINTS[2],
        _TABLE,
        "principal_proceeds_local >= 0 AND accrued_interest_proceeds_local >= 0 "
        "AND embedded_fee_amount_local >= 0 AND embedded_tax_amount_local >= 0",
    )


def downgrade() -> None:
    """Remove redemption terms in reverse dependency order."""

    for constraint_name in reversed(_CONSTRAINTS):
        op.drop_constraint(constraint_name, _TABLE, type_="check")
    for column_name in reversed(_NUMERIC_COLUMNS):
        op.drop_column(_TABLE, column_name)
    op.drop_column(_TABLE, "redemption_price_type")
