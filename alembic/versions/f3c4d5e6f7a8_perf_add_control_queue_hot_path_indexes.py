"""perf add control queue hot path indexes

Revision ID: f3c4d5e6f7a8
Revises: f2b3c4d5e6f7
Create Date: 2026-03-12 00:00:00.000000
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "f3c4d5e6f7a8"
down_revision = "f2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_portfolio_aggregation_jobs_status_aggregation_date",
        "portfolio_aggregation_jobs",
        ["status", "aggregation_date"],
        unique=False,
    )
    op.create_index(
        "ix_portfolio_aggregation_jobs_status_updated_at",
        "portfolio_aggregation_jobs",
        ["status", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_portfolio_valuation_jobs_status_valuation_date",
        "portfolio_valuation_jobs",
        ["status", "valuation_date"],
        unique=False,
    )
    op.create_index(
        "ix_portfolio_valuation_jobs_status_updated_at",
        "portfolio_valuation_jobs",
        ["status", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_reprocessing_jobs_job_type_status_created_at_id",
        "reprocessing_jobs",
        ["job_type", "status", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_reprocessing_jobs_status_updated_at",
        "reprocessing_jobs",
        ["status", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_reprocessing_jobs_status_updated_at", table_name="reprocessing_jobs")
    op.drop_index(
        "ix_reprocessing_jobs_job_type_status_created_at_id",
        table_name="reprocessing_jobs",
    )
    op.drop_index(
        "ix_portfolio_valuation_jobs_status_updated_at",
        table_name="portfolio_valuation_jobs",
    )
    op.drop_index(
        "ix_portfolio_valuation_jobs_status_valuation_date",
        table_name="portfolio_valuation_jobs",
    )
    op.drop_index(
        "ix_portfolio_aggregation_jobs_status_updated_at",
        table_name="portfolio_aggregation_jobs",
    )
    op.drop_index(
        "ix_portfolio_aggregation_jobs_status_aggregation_date",
        table_name="portfolio_aggregation_jobs",
    )
