"""perf: add composite claim index for reprocessing_jobs

Revision ID: b0c1d2e3f4a5
Revises: a1d9c8b7e6f5
Create Date: 2026-03-03 12:00:00
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b0c1d2e3f4a5"
down_revision: Union[str, None] = "a1d9c8b7e6f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "idx_reprocessing_jobs_claim_order",
        "reprocessing_jobs",
        ["job_type", "status", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_reprocessing_jobs_claim_order", table_name="reprocessing_jobs")
