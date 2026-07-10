"""classify corporate action cash consideration as proceeds

Revision ID: c104b2c3d4e9
Revises: c103b2c3d4e8
Create Date: 2026-07-10 00:00:00
"""

from typing import Sequence, Union

from alembic import op

revision: str = "c104b2c3d4e9"
down_revision: Union[str, None] = "c103b2c3d4e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE cashflow_rules
        SET classification = 'CORPORATE_ACTION_PROCEEDS'
        WHERE transaction_type = 'CASH_CONSIDERATION'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE cashflow_rules
        SET classification = 'INCOME'
        WHERE transaction_type = 'CASH_CONSIDERATION'
        """
    )
