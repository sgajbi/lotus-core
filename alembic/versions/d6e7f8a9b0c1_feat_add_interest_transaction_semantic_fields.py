"""feat: add interest semantic fields to transactions

Revision ID: d6e7f8a9b0c1
Revises: b1c2d3e4f5a6
Create Date: 2026-03-05 18:30:00
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d6e7f8a9b0c1"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("interest_direction", sa.String(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("withholding_tax_amount", sa.Numeric(18, 10), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("other_interest_deductions_amount", sa.Numeric(18, 10), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("net_interest_amount", sa.Numeric(18, 10), nullable=True),
    )
    op.create_index(
        "ix_transactions_interest_direction",
        "transactions",
        ["interest_direction"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_interest_direction", table_name="transactions")
    op.drop_column("transactions", "net_interest_amount")
    op.drop_column("transactions", "other_interest_deductions_amount")
    op.drop_column("transactions", "withholding_tax_amount")
    op.drop_column("transactions", "interest_direction")
