"""perf: drop duplicate reprocessing claim index

Revision ID: c0d6e7f8a9b0
Revises: c0d5e6f7a8b9
Create Date: 2026-05-28 21:05:00
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c0d6e7f8a9b0"
down_revision: str | Sequence[str] | None = "c0d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("idx_reprocessing_jobs_claim_order", table_name="reprocessing_jobs")


def downgrade() -> None:
    op.create_index(
        "idx_reprocessing_jobs_claim_order",
        "reprocessing_jobs",
        ["job_type", "status", "created_at", "id"],
        unique=False,
    )
