"""feat: add transaction cash-entry mode and external cash linkage fields

Revision ID: b1c2d3e4f5a6
Revises: f3a4b5c6d7e8
Create Date: 2026-03-05 09:45:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("cash_entry_mode", sa.String(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("external_cash_transaction_id", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_transactions_external_cash_transaction_id",
        "transactions",
        ["external_cash_transaction_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_transactions_external_cash_transaction_id",
        table_name="transactions",
    )
    op.drop_column("transactions", "external_cash_transaction_id")
    op.drop_column("transactions", "cash_entry_mode")
