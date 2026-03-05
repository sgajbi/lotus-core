"""feat: add dual-leg adjustment metadata fields

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-03-05 23:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, None] = "d6e7f8a9b0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("settlement_cash_account_id", sa.String(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("settlement_cash_instrument_id", sa.String(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("movement_direction", sa.String(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("originating_transaction_id", sa.String(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("originating_transaction_type", sa.String(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("adjustment_reason", sa.String(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("link_type", sa.String(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("reconciliation_key", sa.String(), nullable=True),
    )

    op.create_index(
        "ix_transactions_settlement_cash_account_id",
        "transactions",
        ["settlement_cash_account_id"],
        unique=False,
    )
    op.create_index(
        "ix_transactions_originating_transaction_id",
        "transactions",
        ["originating_transaction_id"],
        unique=False,
    )
    op.create_index(
        "ix_transactions_reconciliation_key",
        "transactions",
        ["reconciliation_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_reconciliation_key", table_name="transactions")
    op.drop_index("ix_transactions_originating_transaction_id", table_name="transactions")
    op.drop_index("ix_transactions_settlement_cash_account_id", table_name="transactions")

    op.drop_column("transactions", "reconciliation_key")
    op.drop_column("transactions", "link_type")
    op.drop_column("transactions", "adjustment_reason")
    op.drop_column("transactions", "originating_transaction_type")
    op.drop_column("transactions", "originating_transaction_id")
    op.drop_column("transactions", "movement_direction")
    op.drop_column("transactions", "settlement_cash_instrument_id")
    op.drop_column("transactions", "settlement_cash_account_id")
