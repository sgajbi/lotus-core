"""Persist authoritative source identity on portfolio aggregation jobs.

Revision ID: c127b2c3d500
Revises: c126b2c3d4ff
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c127b2c3d500"
down_revision: str | Sequence[str] | None = "c126b2c3d4ff"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add and backfill epoch/material-revision fences for queued aggregation."""

    op.add_column(
        "portfolio_aggregation_jobs",
        sa.Column("target_epoch", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "portfolio_aggregation_jobs",
        sa.Column("source_revision", sa.Integer(), server_default="1", nullable=False),
    )
    op.execute(
        sa.text(
            """
            UPDATE portfolio_aggregation_jobs AS jobs
            SET target_epoch = COALESCE(
                (
                    SELECT MAX(state.epoch)
                    FROM position_state AS state
                    WHERE BTRIM(state.portfolio_id) = BTRIM(jobs.portfolio_id)
                ),
                0
            )
            """
        )
    )
    op.create_check_constraint(
        "ck_portfolio_aggregation_jobs_target_epoch_nonnegative",
        "portfolio_aggregation_jobs",
        "target_epoch >= 0",
    )
    op.create_check_constraint(
        "ck_portfolio_aggregation_jobs_source_revision_positive",
        "portfolio_aggregation_jobs",
        "source_revision >= 1",
    )


def downgrade() -> None:
    """Remove aggregation source-identity fences."""

    op.drop_constraint(
        "ck_portfolio_aggregation_jobs_source_revision_positive",
        "portfolio_aggregation_jobs",
        type_="check",
    )
    op.drop_constraint(
        "ck_portfolio_aggregation_jobs_target_epoch_nonnegative",
        "portfolio_aggregation_jobs",
        type_="check",
    )
    op.drop_column("portfolio_aggregation_jobs", "source_revision")
    op.drop_column("portfolio_aggregation_jobs", "target_epoch")
