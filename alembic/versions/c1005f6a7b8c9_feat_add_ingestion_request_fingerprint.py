"""Add ingestion request payload fingerprint.

Revision ID: c1005f6a7b8c9
Revises: c1004e5f6a7b8
Create Date: 2026-06-30 11:45:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c1005f6a7b8c9"
down_revision: str | Sequence[str] | None = "c1004e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ingestion_jobs",
        sa.Column("request_payload_fingerprint", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_ingestion_jobs_idempotency_payload_fingerprint",
        "ingestion_jobs",
        ["idempotency_key", "request_payload_fingerprint"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ingestion_jobs_idempotency_payload_fingerprint",
        table_name="ingestion_jobs",
    )
    op.drop_column("ingestion_jobs", "request_payload_fingerprint")
