"""Add reprocessing normalized security support index.

Revision ID: c0e8f9a0b1c2
Revises: c0e7f8a9b0c1
Create Date: 2026-05-29 09:20:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "c0e8f9a0b1c2"
down_revision = "c0e7f8a9b0c1"
branch_labels = None
depends_on = None


INDEX_NAME = "ix_reproc_resetwm_sec_status_created_id"


def upgrade() -> None:
    op.create_index(
        INDEX_NAME,
        "reprocessing_jobs",
        [
            sa.text("trim(payload->>'security_id')"),
            "status",
            "created_at",
            "id",
        ],
        unique=False,
        postgresql_where=sa.text("job_type = 'RESET_WATERMARKS'"),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="reprocessing_jobs")
