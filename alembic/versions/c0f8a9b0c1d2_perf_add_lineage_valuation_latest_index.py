"""Add lineage latest valuation job support index.

Revision ID: c0f8a9b0c1d2
Revises: c0f7a8b9c0d1
Create Date: 2026-05-31 14:20:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "c0f8a9b0c1d2"
down_revision = "c0f7a8b9c0d1"
branch_labels = None
depends_on = None


LINEAGE_VALUATION_LATEST_INDEX = "ix_val_jobs_lineage_latest"


def upgrade() -> None:
    op.create_index(
        LINEAGE_VALUATION_LATEST_INDEX,
        "portfolio_valuation_jobs",
        [
            "portfolio_id",
            sa.text("trim(security_id)"),
            "epoch",
            sa.text("valuation_date DESC"),
            sa.text("id DESC"),
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        LINEAGE_VALUATION_LATEST_INDEX,
        table_name="portfolio_valuation_jobs",
    )
