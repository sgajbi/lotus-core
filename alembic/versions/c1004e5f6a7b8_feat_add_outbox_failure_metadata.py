"""Add durable outbox failure metadata.

Revision ID: c1004e5f6a7b8
Revises: c1003d4e5f6a7
Create Date: 2026-06-30 11:20:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c1004e5f6a7b8"
down_revision: str | Sequence[str] | None = "c1003d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "outbox_events", sa.Column("last_failure_reason_code", sa.String(), nullable=True)
    )
    op.add_column("outbox_events", sa.Column("last_failure_category", sa.String(), nullable=True))
    op.add_column("outbox_events", sa.Column("last_failure_message", sa.String(), nullable=True))
    op.add_column(
        "outbox_events",
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_outbox_events_status_last_failure_at",
        "outbox_events",
        ["status", "last_failure_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_events_status_last_failure_at", table_name="outbox_events")
    op.drop_column("outbox_events", "last_failure_at")
    op.drop_column("outbox_events", "last_failure_message")
    op.drop_column("outbox_events", "last_failure_category")
    op.drop_column("outbox_events", "last_failure_reason_code")
