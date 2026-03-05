"""feat: align TAX cashflow rule as portfolio flow

Revision ID: a9c4d2e8f1b7
Revises: f8a9b0c1d2e3
Create Date: 2026-03-05 11:20:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9c4d2e8f1b7"
down_revision: Union[str, None] = "f8a9b0c1d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE cashflow_rules
            SET is_portfolio_flow = TRUE
            WHERE transaction_type = 'TAX'
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE cashflow_rules
            SET is_portfolio_flow = FALSE
            WHERE transaction_type = 'TAX'
            """
        )
    )
