"""perf add operations support overview indexes

Revision ID: 7f8a9b0c1d2e
Revises: 6f7a8b9c0d1e
Create Date: 2026-05-27 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "7f8a9b0c1d2e"
down_revision: str | Sequence[str] | None = "6f7a8b9c0d1e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_portfolio_aggregation_jobs_portfolio_status_updated",
        "portfolio_aggregation_jobs",
        ["portfolio_id", "status", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_portfolio_aggregation_jobs_portfolio_status_date_updated_id",
        "portfolio_aggregation_jobs",
        ["portfolio_id", "status", "aggregation_date", "updated_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_portfolio_valuation_jobs_portfolio_status_updated",
        "portfolio_valuation_jobs",
        ["portfolio_id", "status", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_portfolio_valuation_jobs_portfolio_status_date_updated_id",
        "portfolio_valuation_jobs",
        ["portfolio_id", "status", "valuation_date", "updated_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_portfolio_valuation_jobs_portfolio_status_date_updated_id",
        table_name="portfolio_valuation_jobs",
    )
    op.drop_index(
        "ix_portfolio_valuation_jobs_portfolio_status_updated",
        table_name="portfolio_valuation_jobs",
    )
    op.drop_index(
        "ix_portfolio_aggregation_jobs_portfolio_status_date_updated_id",
        table_name="portfolio_aggregation_jobs",
    )
    op.drop_index(
        "ix_portfolio_aggregation_jobs_portfolio_status_updated",
        table_name="portfolio_aggregation_jobs",
    )
