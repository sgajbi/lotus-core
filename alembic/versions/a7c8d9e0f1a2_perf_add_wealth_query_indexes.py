"""perf: add wealth query indexes

Revision ID: a7c8d9e0f1a2
Revises: fab7c8d9e0f1
Create Date: 2026-03-27 18:40:00
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c8d9e0f1a2"
down_revision: Union[str, None] = "fab7c8d9e0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_portfolios_booking_center_code",
        "portfolios",
        ["booking_center_code"],
        unique=False,
    )
    op.create_index(
        "ix_transactions_portfolio_instrument_date",
        "transactions",
        ["portfolio_id", "instrument_id", "transaction_date"],
        unique=False,
    )
    op.create_index(
        "ix_transactions_portfolio_settlement_cash_instrument_date",
        "transactions",
        ["portfolio_id", "settlement_cash_instrument_id", "transaction_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_transactions_portfolio_settlement_cash_instrument_date",
        table_name="transactions",
    )
    op.drop_index(
        "ix_transactions_portfolio_instrument_date",
        table_name="transactions",
    )
    op.drop_index(
        "ix_portfolios_booking_center_code",
        table_name="portfolios",
    )
