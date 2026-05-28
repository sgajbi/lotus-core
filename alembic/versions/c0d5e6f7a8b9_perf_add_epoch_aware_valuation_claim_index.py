"""perf add epoch aware valuation claim index

Revision ID: c0d5e6f7a8b9
Revises: c0d4e5f6a7b8
Create Date: 2026-05-28 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c0d5e6f7a8b9"
down_revision: str | Sequence[str] | None = "c0d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index(
        "idx_portfolio_valuation_jobs_claim_order",
        table_name="portfolio_valuation_jobs",
    )
    op.create_index(
        "ix_portfolio_valuation_jobs_claim_order_epoch",
        "portfolio_valuation_jobs",
        [
            "status",
            "portfolio_id",
            "security_id",
            "valuation_date",
            sa.text("epoch DESC"),
            "id",
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_portfolio_valuation_jobs_claim_order_epoch",
        table_name="portfolio_valuation_jobs",
    )
    op.create_index(
        "idx_portfolio_valuation_jobs_claim_order",
        "portfolio_valuation_jobs",
        ["status", "portfolio_id", "security_id", "valuation_date", "id"],
        unique=False,
    )
