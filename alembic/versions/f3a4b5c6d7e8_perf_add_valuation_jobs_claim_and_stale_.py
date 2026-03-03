"""perf: add valuation_jobs claim and stale-scan indexes

Revision ID: f3a4b5c6d7e8
Revises: b0c1d2e3f4a5
Create Date: 2026-03-03 14:15:00
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, None] = "b0c1d2e3f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "idx_portfolio_valuation_jobs_claim_order",
        "portfolio_valuation_jobs",
        ["status", "portfolio_id", "security_id", "valuation_date", "id"],
        unique=False,
    )
    op.create_index(
        "idx_portfolio_valuation_jobs_processing_updated_at",
        "portfolio_valuation_jobs",
        ["status", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_portfolio_valuation_jobs_processing_updated_at",
        table_name="portfolio_valuation_jobs",
    )
    op.drop_index(
        "idx_portfolio_valuation_jobs_claim_order",
        table_name="portfolio_valuation_jobs",
    )
