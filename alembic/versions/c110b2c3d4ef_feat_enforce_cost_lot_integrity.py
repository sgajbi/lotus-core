"""Enforce transaction-cost and position-lot ledger invariants.

Revision ID: c110b2c3d4ef
Revises: c109b2c3d4ee
Create Date: 2026-07-11 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c110b2c3d4ef"
down_revision: str | Sequence[str] | None = "c109b2c3d4ee"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_transaction_costs_amount_positive",
        "transaction_costs",
        "amount > 0",
    )
    op.create_check_constraint(
        "ck_position_lot_open_quantity_nonnegative",
        "position_lot_state",
        "open_quantity >= 0",
    )
    op.create_check_constraint(
        "ck_position_lot_open_not_above_original",
        "position_lot_state",
        "open_quantity <= original_quantity",
    )
    op.create_check_constraint(
        "ck_position_lot_local_cost_nonnegative",
        "position_lot_state",
        "lot_cost_local >= 0",
    )
    op.create_check_constraint(
        "ck_position_lot_base_cost_nonnegative",
        "position_lot_state",
        "lot_cost_base >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_position_lot_base_cost_nonnegative",
        "position_lot_state",
        type_="check",
    )
    op.drop_constraint(
        "ck_position_lot_local_cost_nonnegative",
        "position_lot_state",
        type_="check",
    )
    op.drop_constraint(
        "ck_position_lot_open_not_above_original",
        "position_lot_state",
        type_="check",
    )
    op.drop_constraint(
        "ck_position_lot_open_quantity_nonnegative",
        "position_lot_state",
        type_="check",
    )
    op.drop_constraint(
        "ck_transaction_costs_amount_positive",
        "transaction_costs",
        type_="check",
    )
