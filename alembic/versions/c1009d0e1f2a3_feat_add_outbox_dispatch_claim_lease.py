"""Add outbox dispatch claim lease fields.

Revision ID: c1009d0e1f2a3
Revises: c1008d9e0f1a2
Create Date: 2026-07-01 14:20:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c1009d0e1f2a3"
down_revision: str | Sequence[str] | None = "c1008d9e0f1a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("outbox_events", sa.Column("claim_token", sa.String(length=64), nullable=True))
    op.add_column(
        "outbox_events",
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_outbox_events_status_claim_next_attempt_created_at",
        "outbox_events",
        ["status", "claim_expires_at", "next_attempt_at", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_outbox_events_claim_token",
        "outbox_events",
        ["claim_token"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_events_claim_token", table_name="outbox_events")
    op.drop_index(
        "ix_outbox_events_status_claim_next_attempt_created_at",
        table_name="outbox_events",
    )
    op.drop_column("outbox_events", "claim_expires_at")
    op.drop_column("outbox_events", "claim_token")
