"""classify cash in lieu as fractional position transfer

Revision ID: c107b2c3d4ec
Revises: c106b2c3d4eb
Create Date: 2026-07-10 00:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c107b2c3d4ec"
down_revision: str | Sequence[str] | None = "c106b2c3d4eb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE cashflow_rules
        SET classification = 'TRANSFER', updated_at = CURRENT_TIMESTAMP
        WHERE transaction_type = 'CASH_IN_LIEU'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE cashflow_rules
        SET classification = 'INCOME', updated_at = CURRENT_TIMESTAMP
        WHERE transaction_type = 'CASH_IN_LIEU'
        """
    )
