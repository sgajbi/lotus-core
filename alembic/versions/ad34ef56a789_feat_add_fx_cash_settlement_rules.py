"""feat add fx cash settlement rules

Revision ID: ad34ef56a789
Revises: ac23de45f678
Create Date: 2026-03-09 14:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "ad34ef56a789"
down_revision: Union[str, None] = "ac23de45f678"
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
                ('FX_CASH_SETTLEMENT_BUY', 'FX_BUY', 'EOD', true, false),
                ('FX_CASH_SETTLEMENT_SELL', 'FX_SELL', 'EOD', true, false)
            ON CONFLICT (transaction_type) DO UPDATE
            SET
                classification = EXCLUDED.classification,
                timing = EXCLUDED.timing,
                is_position_flow = EXCLUDED.is_position_flow,
                is_portfolio_flow = EXCLUDED.is_portfolio_flow
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM cashflow_rules
            WHERE transaction_type IN ('FX_CASH_SETTLEMENT_BUY', 'FX_CASH_SETTLEMENT_SELL')
            """
        )
    )
