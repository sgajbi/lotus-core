"""perf add position state hot path indexes

Revision ID: f4d5e6f7a8b9
Revises: f3c4d5e6f7a8
Create Date: 2026-03-12 00:00:00.000000
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "f4d5e6f7a8b9"
down_revision = "f3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_position_state_status_watermark_updated",
        "position_state",
        ["status", "watermark_date", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_position_state_watermark_updated",
        "position_state",
        ["watermark_date", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_position_state_watermark_updated", table_name="position_state")
    op.drop_index("ix_position_state_status_watermark_updated", table_name="position_state")
