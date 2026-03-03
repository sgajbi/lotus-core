"""perf: add ingestion-jobs submitted/completed latency index

Revision ID: e1f2a3b4c7d8
Revises: d0e1f2a3b4c6
Create Date: 2026-03-03 17:10:00
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c7d8"
down_revision: Union[str, None] = "d0e1f2a3b4c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_ingestion_jobs_submitted_completed_at",
        "ingestion_jobs",
        ["submitted_at", "completed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ingestion_jobs_submitted_completed_at", table_name="ingestion_jobs")

