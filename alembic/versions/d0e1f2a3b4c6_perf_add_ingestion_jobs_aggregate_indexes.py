"""perf: add ingestion-jobs aggregate query indexes

Revision ID: d0e1f2a3b4c6
Revises: c8d9e0f1a2b3
Create Date: 2026-03-03 16:45:00
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d0e1f2a3b4c6"
down_revision: Union[str, None] = "c8d9e0f1a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_ingestion_jobs_submitted_at",
        "ingestion_jobs",
        ["submitted_at"],
    )
    op.create_index(
        "ix_ingestion_jobs_status_submitted_at",
        "ingestion_jobs",
        ["status", "submitted_at"],
    )
    op.create_index(
        "ix_ingestion_jobs_idempotency_key_submitted_at",
        "ingestion_jobs",
        ["idempotency_key", "submitted_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ingestion_jobs_idempotency_key_submitted_at", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_status_submitted_at", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_submitted_at", table_name="ingestion_jobs")

