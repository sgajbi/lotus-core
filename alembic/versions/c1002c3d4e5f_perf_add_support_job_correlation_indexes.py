"""Add support job correlation indexes.

Revision ID: c1002c3d4e5f
Revises: c1001b2c3d4e
Create Date: 2026-06-01 01:15:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c1002c3d4e5f"
down_revision: str | Sequence[str] | None = "c1001b2c3d4e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_val_jobs_port_corr_date_updated_id",
        "portfolio_valuation_jobs",
        ["portfolio_id", "correlation_id", "valuation_date", "updated_at", "id"],
        unique=False,
        postgresql_where=sa.text("correlation_id IS NOT NULL"),
    )
    op.create_index(
        "ix_agg_jobs_port_corr_date_updated_id",
        "portfolio_aggregation_jobs",
        ["portfolio_id", "correlation_id", "aggregation_date", "updated_at", "id"],
        unique=False,
        postgresql_where=sa.text("correlation_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agg_jobs_port_corr_date_updated_id",
        table_name="portfolio_aggregation_jobs",
    )
    op.drop_index(
        "ix_val_jobs_port_corr_date_updated_id",
        table_name="portfolio_valuation_jobs",
    )
