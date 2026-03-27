"""perf: add income and activity reporting indexes

Revision ID: b8d9e0f1a2b3
Revises: a7c8d9e0f1a2
Create Date: 2026-03-27 20:30:00
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8d9e0f1a2b3"
down_revision: Union[str, None] = "a7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_transactions_portfolio_type_date",
        "transactions",
        ["portfolio_id", "transaction_type", "transaction_date"],
        unique=False,
    )
    op.create_index(
        "ix_cashflows_portfolio_classification_date",
        "cashflows",
        ["portfolio_id", "classification", "cashflow_date"],
        unique=False,
    )
    op.create_index(
        "ix_cashflows_portfolio_flow_date",
        "cashflows",
        ["portfolio_id", "is_portfolio_flow", "cashflow_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_cashflows_portfolio_flow_date", table_name="cashflows")
    op.drop_index("ix_cashflows_portfolio_classification_date", table_name="cashflows")
    op.drop_index("ix_transactions_portfolio_type_date", table_name="transactions")
