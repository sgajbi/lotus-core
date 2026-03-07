"""feat: add corporate-action expansion cashflow rules

Revision ID: d8e9f0a1b2c3
Revises: c5d6e7f8a9b0
Create Date: 2026-03-07 17:35:00
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, None] = "c5d6e7f8a9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO cashflow_rules (
                transaction_type, classification, timing, is_position_flow, is_portfolio_flow
            )
            VALUES
                ('SPLIT', 'TRANSFER', 'BOD', true, false),
                ('REVERSE_SPLIT', 'TRANSFER', 'EOD', true, false),
                ('CONSOLIDATION', 'TRANSFER', 'EOD', true, false),
                ('BONUS_ISSUE', 'TRANSFER', 'BOD', true, false),
                ('STOCK_DIVIDEND', 'TRANSFER', 'BOD', true, false),
                ('RIGHTS_ANNOUNCE', 'TRANSFER', 'BOD', true, false),
                ('RIGHTS_ALLOCATE', 'TRANSFER', 'BOD', true, false),
                ('RIGHTS_EXPIRE', 'TRANSFER', 'EOD', true, false),
                ('RIGHTS_ADJUSTMENT', 'TRANSFER', 'EOD', true, false),
                ('RIGHTS_SELL', 'TRANSFER', 'EOD', true, false),
                ('RIGHTS_SUBSCRIBE', 'TRANSFER', 'EOD', true, false),
                ('RIGHTS_OVERSUBSCRIBE', 'TRANSFER', 'EOD', true, false),
                ('RIGHTS_REFUND', 'TRANSFER', 'BOD', true, false),
                ('RIGHTS_SHARE_DELIVERY', 'TRANSFER', 'BOD', true, false)
            ON CONFLICT (transaction_type) DO UPDATE SET
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
            WHERE transaction_type IN (
                'SPLIT',
                'REVERSE_SPLIT',
                'CONSOLIDATION',
                'BONUS_ISSUE',
                'STOCK_DIVIDEND',
                'RIGHTS_ANNOUNCE',
                'RIGHTS_ALLOCATE',
                'RIGHTS_EXPIRE',
                'RIGHTS_ADJUSTMENT',
                'RIGHTS_SELL',
                'RIGHTS_SUBSCRIBE',
                'RIGHTS_OVERSUBSCRIBE',
                'RIGHTS_REFUND',
                'RIGHTS_SHARE_DELIVERY'
            )
            """
        )
    )
