"""Add durable outbox retry eligibility.

Revision ID: c1003d4e5f6a7
Revises: c1002c3d4e5f
Create Date: 2026-06-30 11:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c1003d4e5f6a7"
down_revision: str | Sequence[str] | None = "c1002c3d4e5f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "outbox_events",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_outbox_events_status_next_attempt_created_at",
        "outbox_events",
        ["status", "next_attempt_at", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_outbox_events_status_next_attempt_created_at",
        table_name="outbox_events",
    )
    op.drop_column("outbox_events", "next_attempt_at")
