"""perf add replay ordering indexes

Revision ID: f2b3c4d5e6f7
Revises: f1b2c3d4e5f6
Create Date: 2026-03-12 15:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2b3c4d5e6f7"
down_revision: str | Sequence[str] | None = "f1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_instrument_reprocessing_state_impact_updated_security",
        "instrument_reprocessing_state",
        ["earliest_impacted_date", "updated_at", "security_id"],
        unique=False,
    )
    op.create_index(
        "ix_reprocessing_jobs_pending_resetwatermarks_priority",
        "reprocessing_jobs",
        [
            sa.text("(payload->>'earliest_impacted_date')"),
            sa.text("created_at"),
            sa.text("id"),
        ],
        unique=False,
        postgresql_where=sa.text("job_type = 'RESET_WATERMARKS' AND status = 'PENDING'"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_reprocessing_jobs_pending_resetwatermarks_priority",
        table_name="reprocessing_jobs",
        postgresql_where=sa.text("job_type = 'RESET_WATERMARKS' AND status = 'PENDING'"),
    )
    op.drop_index(
        "ix_instrument_reprocessing_state_impact_updated_security",
        table_name="instrument_reprocessing_state",
    )
