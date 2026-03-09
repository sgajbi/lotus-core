"""feat add fx transaction metadata fields

Revision ID: ac23de45f678
Revises: ab12cd34ef56
Create Date: 2026-03-09 11:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "ac23de45f678"
down_revision: Union[str, None] = "ab12cd34ef56"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("component_type", sa.String(), nullable=True))
    op.add_column("transactions", sa.Column("component_id", sa.String(), nullable=True))
    op.add_column("transactions", sa.Column("linked_component_ids", sa.JSON(), nullable=True))
    op.add_column("transactions", sa.Column("fx_cash_leg_role", sa.String(), nullable=True))
    op.add_column("transactions", sa.Column("linked_fx_cash_leg_id", sa.String(), nullable=True))
    op.add_column("transactions", sa.Column("settlement_status", sa.String(), nullable=True))
    op.add_column("transactions", sa.Column("pair_base_currency", sa.String(length=3), nullable=True))
    op.add_column("transactions", sa.Column("pair_quote_currency", sa.String(length=3), nullable=True))
    op.add_column("transactions", sa.Column("fx_rate_quote_convention", sa.String(), nullable=True))
    op.add_column("transactions", sa.Column("buy_currency", sa.String(length=3), nullable=True))
    op.add_column("transactions", sa.Column("sell_currency", sa.String(length=3), nullable=True))
    op.add_column("transactions", sa.Column("buy_amount", sa.Numeric(18, 10), nullable=True))
    op.add_column("transactions", sa.Column("sell_amount", sa.Numeric(18, 10), nullable=True))
    op.add_column("transactions", sa.Column("contract_rate", sa.Numeric(18, 10), nullable=True))
    op.add_column("transactions", sa.Column("fx_contract_id", sa.String(), nullable=True))
    op.add_column(
        "transactions", sa.Column("fx_contract_open_transaction_id", sa.String(), nullable=True)
    )
    op.add_column(
        "transactions", sa.Column("fx_contract_close_transaction_id", sa.String(), nullable=True)
    )
    op.add_column("transactions", sa.Column("settlement_of_fx_contract_id", sa.String(), nullable=True))
    op.add_column("transactions", sa.Column("swap_event_id", sa.String(), nullable=True))
    op.add_column("transactions", sa.Column("near_leg_group_id", sa.String(), nullable=True))
    op.add_column("transactions", sa.Column("far_leg_group_id", sa.String(), nullable=True))
    op.add_column("transactions", sa.Column("spot_exposure_model", sa.String(), nullable=True))
    op.add_column("transactions", sa.Column("fx_realized_pnl_mode", sa.String(), nullable=True))
    op.add_column("transactions", sa.Column("realized_capital_pnl_local", sa.Numeric(18, 10), nullable=True))
    op.add_column("transactions", sa.Column("realized_fx_pnl_local", sa.Numeric(18, 10), nullable=True))
    op.add_column("transactions", sa.Column("realized_total_pnl_local", sa.Numeric(18, 10), nullable=True))
    op.add_column("transactions", sa.Column("realized_capital_pnl_base", sa.Numeric(18, 10), nullable=True))
    op.add_column("transactions", sa.Column("realized_fx_pnl_base", sa.Numeric(18, 10), nullable=True))
    op.add_column("transactions", sa.Column("realized_total_pnl_base", sa.Numeric(18, 10), nullable=True))

    op.create_index(op.f("ix_transactions_component_type"), "transactions", ["component_type"], unique=False)
    op.create_index(op.f("ix_transactions_component_id"), "transactions", ["component_id"], unique=False)
    op.create_index(op.f("ix_transactions_fx_cash_leg_role"), "transactions", ["fx_cash_leg_role"], unique=False)
    op.create_index(op.f("ix_transactions_linked_fx_cash_leg_id"), "transactions", ["linked_fx_cash_leg_id"], unique=False)
    op.create_index(op.f("ix_transactions_settlement_status"), "transactions", ["settlement_status"], unique=False)
    op.create_index(op.f("ix_transactions_fx_contract_id"), "transactions", ["fx_contract_id"], unique=False)
    op.create_index(
        op.f("ix_transactions_fx_contract_open_transaction_id"),
        "transactions",
        ["fx_contract_open_transaction_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_transactions_fx_contract_close_transaction_id"),
        "transactions",
        ["fx_contract_close_transaction_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_transactions_settlement_of_fx_contract_id"),
        "transactions",
        ["settlement_of_fx_contract_id"],
        unique=False,
    )
    op.create_index(op.f("ix_transactions_swap_event_id"), "transactions", ["swap_event_id"], unique=False)
    op.create_index(op.f("ix_transactions_near_leg_group_id"), "transactions", ["near_leg_group_id"], unique=False)
    op.create_index(op.f("ix_transactions_far_leg_group_id"), "transactions", ["far_leg_group_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_transactions_far_leg_group_id"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_near_leg_group_id"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_swap_event_id"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_settlement_of_fx_contract_id"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_fx_contract_close_transaction_id"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_fx_contract_open_transaction_id"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_fx_contract_id"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_settlement_status"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_linked_fx_cash_leg_id"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_fx_cash_leg_role"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_component_id"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_component_type"), table_name="transactions")

    op.drop_column("transactions", "realized_total_pnl_base")
    op.drop_column("transactions", "realized_fx_pnl_base")
    op.drop_column("transactions", "realized_capital_pnl_base")
    op.drop_column("transactions", "realized_total_pnl_local")
    op.drop_column("transactions", "realized_fx_pnl_local")
    op.drop_column("transactions", "realized_capital_pnl_local")
    op.drop_column("transactions", "fx_realized_pnl_mode")
    op.drop_column("transactions", "spot_exposure_model")
    op.drop_column("transactions", "far_leg_group_id")
    op.drop_column("transactions", "near_leg_group_id")
    op.drop_column("transactions", "swap_event_id")
    op.drop_column("transactions", "settlement_of_fx_contract_id")
    op.drop_column("transactions", "fx_contract_close_transaction_id")
    op.drop_column("transactions", "fx_contract_open_transaction_id")
    op.drop_column("transactions", "fx_contract_id")
    op.drop_column("transactions", "contract_rate")
    op.drop_column("transactions", "sell_amount")
    op.drop_column("transactions", "buy_amount")
    op.drop_column("transactions", "sell_currency")
    op.drop_column("transactions", "buy_currency")
    op.drop_column("transactions", "fx_rate_quote_convention")
    op.drop_column("transactions", "pair_quote_currency")
    op.drop_column("transactions", "pair_base_currency")
    op.drop_column("transactions", "settlement_status")
    op.drop_column("transactions", "linked_fx_cash_leg_id")
    op.drop_column("transactions", "fx_cash_leg_role")
    op.drop_column("transactions", "linked_component_ids")
    op.drop_column("transactions", "component_id")
    op.drop_column("transactions", "component_type")
