"""Add position timeseries latest-before support index.

Revision ID: c0fbb2c3d4e5
Revises: c0faa1b2c3d4
Create Date: 2026-05-31 15:25:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "c0fbb2c3d4e5"
down_revision = "c0faa1b2c3d4"
branch_labels = None
depends_on = None


POSITION_TIMESERIES_LATEST_INDEX = "ix_pos_ts_port_norm_sec_date_epoch"


def upgrade() -> None:
    op.create_index(
        POSITION_TIMESERIES_LATEST_INDEX,
        "position_timeseries",
        [
            "portfolio_id",
            sa.text("trim(security_id)"),
            sa.text("date DESC"),
            sa.text("epoch DESC"),
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        POSITION_TIMESERIES_LATEST_INDEX,
        table_name="position_timeseries",
    )
