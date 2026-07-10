"""add position transaction lineage index

Revision ID: c109b2c3d4ee
Revises: c108b2c3d4ed
Create Date: 2026-07-11 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c109b2c3d4ee"
down_revision: str | Sequence[str] | None = "c108b2c3d4ed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_pos_hist_norm_port_sec_epoch_txn",
        "position_history",
        [
            sa.text("trim(portfolio_id)"),
            sa.text("trim(security_id)"),
            "epoch",
            sa.text("trim(transaction_id)"),
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_pos_hist_norm_port_sec_epoch_txn",
        table_name="position_history",
    )
