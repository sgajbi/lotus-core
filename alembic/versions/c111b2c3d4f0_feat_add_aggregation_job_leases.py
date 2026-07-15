"""Add ownership leases to portfolio aggregation jobs.

Revision ID: c111b2c3d4f0
Revises: c110b2c3d4ef
Create Date: 2026-07-15 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c111b2c3d4f0"
down_revision: str | Sequence[str] | None = "c110b2c3d4ef"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add nullable lease identity with an all-or-none integrity contract."""

    op.add_column(
        "portfolio_aggregation_jobs",
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "portfolio_aggregation_jobs",
        sa.Column("lease_token", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "portfolio_aggregation_jobs",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_portfolio_aggregation_jobs_lease_complete",
        "portfolio_aggregation_jobs",
        "(lease_owner IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL) OR "
        "(lease_owner IS NOT NULL AND lease_token IS NOT NULL AND "
        "lease_expires_at IS NOT NULL)",
    )
    op.create_index(
        "ix_portfolio_aggregation_jobs_status_lease_expiry",
        "portfolio_aggregation_jobs",
        ["status", "lease_expires_at"],
        unique=False,
    )


def downgrade() -> None:
    """Remove aggregation lease identity and expiry lookup support."""

    op.drop_index(
        "ix_portfolio_aggregation_jobs_status_lease_expiry",
        table_name="portfolio_aggregation_jobs",
    )
    op.drop_constraint(
        "ck_portfolio_aggregation_jobs_lease_complete",
        "portfolio_aggregation_jobs",
        type_="check",
    )
    op.drop_column("portfolio_aggregation_jobs", "lease_expires_at")
    op.drop_column("portfolio_aggregation_jobs", "lease_token")
    op.drop_column("portfolio_aggregation_jobs", "lease_owner")
