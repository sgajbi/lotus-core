"""Index unresolved outbox events by ordered Kafka stream.

Revision ID: c129b2c3d502
Revises: c128b2c3d501
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c129b2c3d502"
down_revision: str | Sequence[str] | None = "c128b2c3d501"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Support bounded stream-head lookup for unresolved outbox events."""

    op.create_index(
        "ix_outbox_events_stream_unresolved_order",
        "outbox_events",
        ["topic", "partition_key", "created_at", "id"],
        unique=False,
        postgresql_where=sa.text("status IN ('PENDING', 'FAILED')"),
    )


def downgrade() -> None:
    """Remove the unresolved stream-order lookup index."""

    op.drop_index(
        "ix_outbox_events_stream_unresolved_order",
        table_name="outbox_events",
    )
