"""perf: add aggregation claim order index

Revision ID: c0d7e8f9a0b1
Revises: c0d6e7f8a9b0
Create Date: 2026-05-28 21:12:00
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c0d7e8f9a0b1"
down_revision: str | Sequence[str] | None = "c0d6e7f8a9b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_portfolio_aggregation_jobs_claim_order",
        "portfolio_aggregation_jobs",
        ["status", "portfolio_id", "aggregation_date", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_portfolio_aggregation_jobs_claim_order",
        table_name="portfolio_aggregation_jobs",
    )
