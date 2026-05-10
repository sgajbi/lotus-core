"""feat: enrich mandate binding with objective and review cadence

Revision ID: 4d5e6f7a8b9c
Revises: 3c4d5e6f7a8b
Create Date: 2026-05-10
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "4d5e6f7a8b9c"
down_revision: Union[str, None] = "3c4d5e6f7a8b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "portfolio_mandate_bindings",
        sa.Column("mandate_objective", sa.String(), nullable=True),
    )
    op.add_column(
        "portfolio_mandate_bindings",
        sa.Column("review_cadence", sa.String(), nullable=True),
    )
    op.add_column(
        "portfolio_mandate_bindings",
        sa.Column("last_review_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "portfolio_mandate_bindings",
        sa.Column("next_review_due_date", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("portfolio_mandate_bindings", "next_review_due_date")
    op.drop_column("portfolio_mandate_bindings", "last_review_date")
    op.drop_column("portfolio_mandate_bindings", "review_cadence")
    op.drop_column("portfolio_mandate_bindings", "mandate_objective")
