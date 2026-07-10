"""add unrealized price and FX PnL components

Revision ID: c101b2c3d4e6
Revises: c100b2c3d4e5
Create Date: 2026-07-10 00:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "c101b2c3d4e6"
down_revision: Union[str, None] = "c100b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "daily_position_snapshots",
        sa.Column("unrealized_price_gain_loss", sa.Numeric(18, 10), nullable=True),
    )
    op.add_column(
        "daily_position_snapshots",
        sa.Column("unrealized_fx_gain_loss", sa.Numeric(18, 10), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("daily_position_snapshots", "unrealized_fx_gain_loss")
    op.drop_column("daily_position_snapshots", "unrealized_price_gain_loss")
