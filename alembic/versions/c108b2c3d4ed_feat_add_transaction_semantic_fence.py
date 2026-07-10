"""add transaction semantic processing fence

Revision ID: c108b2c3d4ed
Revises: c107b2c3d4ec
Create Date: 2026-07-11 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c108b2c3d4ed"
down_revision: str | Sequence[str] | None = "c107b2c3d4ec"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("processed_events", sa.Column("semantic_key", sa.String(), nullable=True))
    op.add_column(
        "processed_events",
        sa.Column("payload_fingerprint", sa.String(), nullable=True),
    )
    op.create_index(
        "uq_processed_events_service_semantic_key",
        "processed_events",
        ["service_name", "semantic_key"],
        unique=True,
        postgresql_where=sa.text("semantic_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_processed_events_service_semantic_key",
        table_name="processed_events",
    )
    op.drop_column("processed_events", "payload_fingerprint")
    op.drop_column("processed_events", "semantic_key")
