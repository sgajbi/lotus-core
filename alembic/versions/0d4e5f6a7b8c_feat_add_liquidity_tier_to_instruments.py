"""feat_add_liquidity_tier_to_instruments

Revision ID: 0d4e5f6a7b8c
Revises: c9e0f1a2b3c4
Create Date: 2026-04-07 18:20:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0d4e5f6a7b8c"
down_revision: Union[str, None] = "c9e0f1a2b3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "instruments",
        sa.Column("liquidity_tier", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("instruments", "liquidity_tier")
