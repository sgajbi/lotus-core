"""Add bounded FX revaluation queue indexes.

Revision ID: c112b2c3d4f1
Revises: c111b2c3d4f0
Create Date: 2026-07-15 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c112b2c3d4f1"
down_revision: str | Sequence[str] | None = "c111b2c3d4f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Enforce one pending replay job per direct currency pair."""
    op.create_index(
        "uq_reproc_jobs_pending_fx_pair",
        "reprocessing_jobs",
        [
            sa.text("(payload->>'from_currency')"),
            sa.text("(payload->>'to_currency')"),
        ],
        unique=True,
        postgresql_where=sa.text(
            "job_type = 'RESET_FX_WATERMARKS' AND status = 'PENDING'"
        ),
    )
    op.create_index(
        "ix_reproc_jobs_pending_fx_priority",
        "reprocessing_jobs",
        [
            sa.text("(payload->>'earliest_impacted_date')"),
            "created_at",
            "id",
        ],
        unique=False,
        postgresql_where=sa.text(
            "job_type = 'RESET_FX_WATERMARKS' AND status = 'PENDING'"
        ),
    )


def downgrade() -> None:
    """Remove FX revaluation queue indexes."""
    op.drop_index("ix_reproc_jobs_pending_fx_priority", table_name="reprocessing_jobs")
    op.drop_index("uq_reproc_jobs_pending_fx_pair", table_name="reprocessing_jobs")
