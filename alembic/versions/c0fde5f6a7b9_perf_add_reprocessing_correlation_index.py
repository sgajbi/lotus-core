"""Add reprocessing correlation support index.

Revision ID: c0fde5f6a7b9
Revises: c0fdd4e5f6a8
Create Date: 2026-05-31 20:10:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "c0fde5f6a7b9"
down_revision = "c0fdd4e5f6a8"
branch_labels = None
depends_on = None


INDEX_NAME = "ix_reproc_resetwm_corr_status_created_id"


def upgrade() -> None:
    op.create_index(
        INDEX_NAME,
        "reprocessing_jobs",
        ["correlation_id", "status", "created_at", "id"],
        unique=False,
        postgresql_where=sa.text("job_type = 'RESET_WATERMARKS'"),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="reprocessing_jobs")
