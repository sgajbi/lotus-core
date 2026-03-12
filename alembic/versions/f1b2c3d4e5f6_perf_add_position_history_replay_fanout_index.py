"""perf add position history replay fanout index

Revision ID: f1b2c3d4e5f6
Revises: f0a1b2c3d4e5
Create Date: 2026-03-12 19:10:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "f1b2c3d4e5f6"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_position_history_security_epoch_date_id_portfolio",
        "position_history",
        [
            "security_id",
            "epoch",
            sa.text("position_date DESC"),
            sa.text("id DESC"),
            "portfolio_id",
        ],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_position_history_security_epoch_date_id_portfolio",
        table_name="position_history",
    )
