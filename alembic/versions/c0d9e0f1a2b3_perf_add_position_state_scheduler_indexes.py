"""perf: add position state scheduler indexes

Revision ID: c0d9e0f1a2b3
Revises: c0d8e9f0a1b2
Create Date: 2026-05-29 09:35:00
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c0d9e0f1a2b3"
down_revision: str | Sequence[str] | None = "c0d8e9f0a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_position_state_updated_watermark_key",
        "position_state",
        ["updated_at", "watermark_date", "portfolio_id", "security_id"],
        unique=False,
    )
    op.create_index(
        "ix_position_state_status_updated_watermark_key",
        "position_state",
        ["status", "updated_at", "watermark_date", "portfolio_id", "security_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_position_state_status_updated_watermark_key",
        table_name="position_state",
    )
    op.drop_index("ix_position_state_updated_watermark_key", table_name="position_state")
