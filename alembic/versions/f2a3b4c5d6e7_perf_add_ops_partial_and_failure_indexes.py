"""perf: add ops partial backlog index and failure-history index

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c7d8
Create Date: 2026-03-03 17:45:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, None] = "e1f2a3b4c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_ingestion_job_failures_job_failed_at",
        "ingestion_job_failures",
        ["job_id", "failed_at"],
    )
    op.create_index(
        "ix_ingestion_jobs_non_terminal_submitted_at",
        "ingestion_jobs",
        ["submitted_at"],
        postgresql_where=sa.text("status IN ('accepted', 'queued')"),
    )


def downgrade() -> None:
    op.drop_index("ix_ingestion_jobs_non_terminal_submitted_at", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_job_failures_job_failed_at", table_name="ingestion_job_failures")

