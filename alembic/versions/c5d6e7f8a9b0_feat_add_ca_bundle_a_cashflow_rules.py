"""feat: add corporate-action bundle A cashflow rules

Revision ID: c5d6e7f8a9b0
Revises: b4d5e6f7a8b9
Create Date: 2026-03-07 23:20:00
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, None] = "b4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO cashflow_rules (
                transaction_type, classification, timing, is_position_flow, is_portfolio_flow
            )
            VALUES
                ('SPIN_OFF', 'TRANSFER', 'EOD', true, false),
                ('SPIN_IN', 'TRANSFER', 'BOD', true, false),
                ('DEMERGER_OUT', 'TRANSFER', 'EOD', true, false),
                ('DEMERGER_IN', 'TRANSFER', 'BOD', true, false),
                ('CASH_CONSIDERATION', 'INCOME', 'EOD', true, false)
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
                'SPIN_OFF',
                'SPIN_IN',
                'DEMERGER_OUT',
                'DEMERGER_IN',
                'CASH_CONSIDERATION'
            )
            """
        )
    )
