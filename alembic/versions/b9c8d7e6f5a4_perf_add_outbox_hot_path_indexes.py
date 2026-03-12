"""perf add outbox hot path indexes

Revision ID: b9c8d7e6f5a4
Revises: f3c4d5e6f7a8
Create Date: 2026-03-12 18:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b9c8d7e6f5a4"
down_revision: str | Sequence[str] | None = "f4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_outbox_events_status_created_at",
        "outbox_events",
        ["status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_outbox_events_status_last_attempted_at",
        "outbox_events",
        ["status", "last_attempted_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_events_status_last_attempted_at", table_name="outbox_events")
    op.drop_index("ix_outbox_events_status_created_at", table_name="outbox_events")
