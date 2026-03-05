"""feat: add adjustment cashflow rule

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-03-05 23:25:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f8a9b0c1d2e3"
down_revision: Union[str, None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO cashflow_rules (
                transaction_type, classification, timing, is_position_flow, is_portfolio_flow
            )
            VALUES (
                'ADJUSTMENT', 'TRANSFER', 'EOD', true, false
            )
            ON CONFLICT (transaction_type) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM cashflow_rules WHERE transaction_type = 'ADJUSTMENT'"))
