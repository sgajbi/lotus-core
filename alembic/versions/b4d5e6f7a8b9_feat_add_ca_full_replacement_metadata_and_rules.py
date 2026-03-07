"""feat: add corporate-action full replacement metadata and cashflow rules

Revision ID: b4d5e6f7a8b9
Revises: a9c4d2e8f1b7
Create Date: 2026-03-07 19:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4d5e6f7a8b9"
down_revision: Union[str, None] = "a9c4d2e8f1b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("parent_transaction_reference", sa.String(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("linked_parent_event_id", sa.String(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("parent_event_reference", sa.String(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("child_role", sa.String(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("child_sequence_hint", sa.Integer(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("dependency_reference_ids", sa.JSON(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("source_instrument_id", sa.String(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("target_instrument_id", sa.String(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("source_transaction_reference", sa.String(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("target_transaction_reference", sa.String(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("linked_cash_transaction_id", sa.String(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("has_synthetic_flow", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("synthetic_flow_effective_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("synthetic_flow_amount_local", sa.Numeric(18, 10), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("synthetic_flow_currency", sa.String(length=3), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("synthetic_flow_amount_base", sa.Numeric(18, 10), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("synthetic_flow_fx_rate_to_base", sa.Numeric(18, 10), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("synthetic_flow_price_used", sa.Numeric(18, 10), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("synthetic_flow_quantity_used", sa.Numeric(18, 10), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("synthetic_flow_valuation_method", sa.String(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("synthetic_flow_classification", sa.String(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("synthetic_flow_price_source", sa.String(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("synthetic_flow_fx_source", sa.String(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("synthetic_flow_source", sa.String(), nullable=True),
    )

    op.create_index(
        "ix_transactions_parent_transaction_reference",
        "transactions",
        ["parent_transaction_reference"],
        unique=False,
    )
    op.create_index(
        "ix_transactions_linked_parent_event_id",
        "transactions",
        ["linked_parent_event_id"],
        unique=False,
    )
    op.create_index(
        "ix_transactions_parent_event_reference",
        "transactions",
        ["parent_event_reference"],
        unique=False,
    )
    op.create_index(
        "ix_transactions_source_instrument_id",
        "transactions",
        ["source_instrument_id"],
        unique=False,
    )
    op.create_index(
        "ix_transactions_target_instrument_id",
        "transactions",
        ["target_instrument_id"],
        unique=False,
    )
    op.create_index(
        "ix_transactions_source_transaction_reference",
        "transactions",
        ["source_transaction_reference"],
        unique=False,
    )
    op.create_index(
        "ix_transactions_target_transaction_reference",
        "transactions",
        ["target_transaction_reference"],
        unique=False,
    )
    op.create_index(
        "ix_transactions_linked_cash_transaction_id",
        "transactions",
        ["linked_cash_transaction_id"],
        unique=False,
    )
    op.create_index(
        "ix_transactions_synthetic_flow_effective_date",
        "transactions",
        ["synthetic_flow_effective_date"],
        unique=False,
    )
    op.create_index(
        "ix_transactions_synthetic_flow_classification",
        "transactions",
        ["synthetic_flow_classification"],
        unique=False,
    )

    op.execute(
        sa.text(
            """
            INSERT INTO cashflow_rules (
                transaction_type, classification, timing, is_position_flow, is_portfolio_flow
            )
            VALUES
                ('MERGER_OUT', 'TRANSFER', 'EOD', true, false),
                ('MERGER_IN', 'TRANSFER', 'BOD', true, false),
                ('EXCHANGE_OUT', 'TRANSFER', 'EOD', true, false),
                ('EXCHANGE_IN', 'TRANSFER', 'BOD', true, false),
                ('REPLACEMENT_OUT', 'TRANSFER', 'EOD', true, false),
                ('REPLACEMENT_IN', 'TRANSFER', 'BOD', true, false),
                ('CASH_IN_LIEU', 'INCOME', 'EOD', true, false)
            ON CONFLICT (transaction_type) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM cashflow_rules
            WHERE transaction_type IN (
                'MERGER_OUT',
                'MERGER_IN',
                'EXCHANGE_OUT',
                'EXCHANGE_IN',
                'REPLACEMENT_OUT',
                'REPLACEMENT_IN',
                'CASH_IN_LIEU'
            )
            """
        )
    )

    op.drop_index("ix_transactions_synthetic_flow_classification", table_name="transactions")
    op.drop_index("ix_transactions_synthetic_flow_effective_date", table_name="transactions")
    op.drop_index("ix_transactions_linked_cash_transaction_id", table_name="transactions")
    op.drop_index("ix_transactions_target_transaction_reference", table_name="transactions")
    op.drop_index("ix_transactions_source_transaction_reference", table_name="transactions")
    op.drop_index("ix_transactions_target_instrument_id", table_name="transactions")
    op.drop_index("ix_transactions_source_instrument_id", table_name="transactions")
    op.drop_index("ix_transactions_parent_event_reference", table_name="transactions")
    op.drop_index("ix_transactions_linked_parent_event_id", table_name="transactions")
    op.drop_index("ix_transactions_parent_transaction_reference", table_name="transactions")

    op.drop_column("transactions", "synthetic_flow_source")
    op.drop_column("transactions", "synthetic_flow_fx_source")
    op.drop_column("transactions", "synthetic_flow_price_source")
    op.drop_column("transactions", "synthetic_flow_classification")
    op.drop_column("transactions", "synthetic_flow_valuation_method")
    op.drop_column("transactions", "synthetic_flow_quantity_used")
    op.drop_column("transactions", "synthetic_flow_price_used")
    op.drop_column("transactions", "synthetic_flow_fx_rate_to_base")
    op.drop_column("transactions", "synthetic_flow_amount_base")
    op.drop_column("transactions", "synthetic_flow_currency")
    op.drop_column("transactions", "synthetic_flow_amount_local")
    op.drop_column("transactions", "synthetic_flow_effective_date")
    op.drop_column("transactions", "has_synthetic_flow")
    op.drop_column("transactions", "linked_cash_transaction_id")
    op.drop_column("transactions", "target_transaction_reference")
    op.drop_column("transactions", "source_transaction_reference")
    op.drop_column("transactions", "target_instrument_id")
    op.drop_column("transactions", "source_instrument_id")
    op.drop_column("transactions", "dependency_reference_ids")
    op.drop_column("transactions", "child_sequence_hint")
    op.drop_column("transactions", "child_role")
    op.drop_column("transactions", "parent_event_reference")
    op.drop_column("transactions", "linked_parent_event_id")
    op.drop_column("transactions", "parent_transaction_reference")
