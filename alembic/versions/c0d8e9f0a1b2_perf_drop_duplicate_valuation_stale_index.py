"""perf: drop duplicate valuation stale index

Revision ID: c0d8e9f0a1b2
Revises: c0d7e8f9a0b1
Create Date: 2026-05-28 21:22:00
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c0d8e9f0a1b2"
down_revision: str | Sequence[str] | None = "c0d7e8f9a0b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index(
        "idx_portfolio_valuation_jobs_processing_updated_at",
        table_name="portfolio_valuation_jobs",
    )


def downgrade() -> None:
    op.create_index(
        "idx_portfolio_valuation_jobs_processing_updated_at",
        "portfolio_valuation_jobs",
        ["status", "updated_at"],
        unique=False,
    )
