"""Add lineage latest history and snapshot support indexes.

Revision ID: c0f9a0b1c2d3
Revises: c0f8a9b0c1d2
Create Date: 2026-05-31 14:35:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "c0f9a0b1c2d3"
down_revision = "c0f8a9b0c1d2"
branch_labels = None
depends_on = None


LINEAGE_HISTORY_LATEST_INDEX = "ix_pos_hist_lineage_latest"
LINEAGE_SNAPSHOT_LATEST_INDEX = "ix_daily_snap_lineage_latest"


def upgrade() -> None:
    op.create_index(
        LINEAGE_HISTORY_LATEST_INDEX,
        "position_history",
        [
            "portfolio_id",
            sa.text("trim(security_id)"),
            "epoch",
            sa.text("position_date DESC"),
        ],
        unique=False,
    )
    op.create_index(
        LINEAGE_SNAPSHOT_LATEST_INDEX,
        "daily_position_snapshots",
        [
            "portfolio_id",
            sa.text("trim(security_id)"),
            "epoch",
            sa.text("date DESC"),
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        LINEAGE_SNAPSHOT_LATEST_INDEX,
        table_name="daily_position_snapshots",
    )
    op.drop_index(
        LINEAGE_HISTORY_LATEST_INDEX,
        table_name="position_history",
    )
