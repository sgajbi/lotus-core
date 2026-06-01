"""perf add api query hot path indexes

Revision ID: a0b1c2d3e4f5
Revises: 9b0c1d2e3f4a
Create Date: 2026-05-28 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a0b1c2d3e4f5"
down_revision: str | Sequence[str] | None = "9b0c1d2e3f4a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_pos_hist_port_norm_sec_date_id",
        "position_history",
        [
            "portfolio_id",
            sa.text("trim(security_id)"),
            sa.text("position_date DESC"),
            sa.text("id DESC"),
            "epoch",
        ],
        unique=False,
    )
    op.create_index(
        "ix_daily_snap_port_norm_sec_date_id",
        "daily_position_snapshots",
        [
            "portfolio_id",
            sa.text("trim(security_id)"),
            sa.text("date DESC"),
            sa.text("id DESC"),
            "epoch",
        ],
        unique=False,
    )
    op.create_index(
        "ix_cash_account_port_currency_id",
        "cash_account_masters",
        ["portfolio_id", "account_currency", "cash_account_id"],
        unique=False,
    )
    op.create_index(
        "ix_lookthrough_norm_parent_eff_comp",
        "instrument_lookthrough_components",
        [
            sa.text("trim(parent_security_id)"),
            sa.text("effective_from DESC"),
            "effective_to",
            sa.text("trim(component_security_id)"),
        ],
        unique=False,
    )
    op.create_index(
        "ix_txn_port_date_id",
        "transactions",
        ["portfolio_id", sa.text("transaction_date DESC"), sa.text("id DESC")],
        unique=False,
    )
    op.create_index(
        "ix_txn_port_norm_sec_date_id",
        "transactions",
        [
            "portfolio_id",
            sa.text("trim(security_id)"),
            sa.text("transaction_date DESC"),
            sa.text("id DESC"),
        ],
        unique=False,
    )
    op.create_index(
        "ix_txn_port_norm_cash_instr_date_id",
        "transactions",
        [
            "portfolio_id",
            sa.text("trim(settlement_cash_instrument_id)"),
            sa.text("transaction_date DESC"),
            sa.text("id DESC"),
        ],
        unique=False,
    )
    op.create_index(
        "ix_txn_port_linked_group_date_id",
        "transactions",
        [
            "portfolio_id",
            "linked_transaction_group_id",
            sa.text("transaction_date DESC"),
            sa.text("id DESC"),
        ],
        unique=False,
    )
    op.create_index(
        "ix_position_state_port_norm_sec_epoch",
        "position_state",
        ["portfolio_id", sa.text("trim(security_id)"), "epoch"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_position_state_port_norm_sec_epoch", table_name="position_state")
    op.drop_index("ix_txn_port_linked_group_date_id", table_name="transactions")
    op.drop_index("ix_txn_port_norm_cash_instr_date_id", table_name="transactions")
    op.drop_index("ix_txn_port_norm_sec_date_id", table_name="transactions")
    op.drop_index("ix_txn_port_date_id", table_name="transactions")
    op.drop_index(
        "ix_lookthrough_norm_parent_eff_comp",
        table_name="instrument_lookthrough_components",
    )
    op.drop_index("ix_cash_account_port_currency_id", table_name="cash_account_masters")
    op.drop_index(
        "ix_daily_snap_port_norm_sec_date_id",
        table_name="daily_position_snapshots",
    )
    op.drop_index("ix_pos_hist_port_norm_sec_date_id", table_name="position_history")
