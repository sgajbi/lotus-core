"""Separate durable aggregate identity from Kafka partition identity.

Revision ID: c113b2c3d4f2
Revises: c112b2c3d4f1
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c113b2c3d4f2"
down_revision: str | None = "c112b2c3d4f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Backfill legacy outbox rows before enforcing explicit partition identity."""

    op.add_column("outbox_events", sa.Column("partition_key", sa.String(), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE outbox_events
            SET partition_key = aggregate_id
            WHERE partition_key IS NULL
            """
        )
    )
    op.alter_column("outbox_events", "partition_key", nullable=False)


def downgrade() -> None:
    """Remove the explicit outbox partition identity."""

    op.drop_column("outbox_events", "partition_key")
