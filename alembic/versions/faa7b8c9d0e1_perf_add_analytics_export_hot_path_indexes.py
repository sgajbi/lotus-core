"""perf add analytics export hot path indexes

Revision ID: faa7b8c9d0e1
Revises: f5e6f7a8b9c0
Create Date: 2026-03-13 21:05:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "faa7b8c9d0e1"
down_revision: str | Sequence[str] | None = "f5e6f7a8b9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_analytics_export_jobs_portfolio_status_created_at",
        "analytics_export_jobs",
        ["portfolio_id", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_analytics_export_jobs_status_updated_at",
        "analytics_export_jobs",
        ["status", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_analytics_export_jobs_status_updated_at", table_name="analytics_export_jobs")
    op.drop_index(
        "ix_analytics_export_jobs_portfolio_status_created_at",
        table_name="analytics_export_jobs",
    )
