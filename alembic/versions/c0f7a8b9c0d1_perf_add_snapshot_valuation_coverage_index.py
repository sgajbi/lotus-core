"""Add snapshot valuation coverage support index.

Revision ID: c0f7a8b9c0d1
Revises: c0f6a7b8c9d0
Create Date: 2026-05-31 14:05:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "c0f7a8b9c0d1"
down_revision = "c0f6a7b8c9d0"
branch_labels = None
depends_on = None


SNAPSHOT_VALUATION_COVERAGE_INDEX = "ix_daily_snap_port_date_status_norm_sec_epoch"


def upgrade() -> None:
    op.execute(
        "UPDATE daily_position_snapshots "
        "SET valuation_status = upper(trim(valuation_status)) "
        "WHERE valuation_status IS NOT NULL"
    )
    op.create_index(
        SNAPSHOT_VALUATION_COVERAGE_INDEX,
        "daily_position_snapshots",
        [
            "portfolio_id",
            "date",
            "valuation_status",
            sa.text("trim(security_id)"),
            "epoch",
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        SNAPSHOT_VALUATION_COVERAGE_INDEX,
        table_name="daily_position_snapshots",
    )
    # Snapshot valuation-status canonicalization is intentionally irreversible.
