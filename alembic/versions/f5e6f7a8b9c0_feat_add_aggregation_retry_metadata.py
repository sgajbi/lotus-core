"""add aggregation retry metadata

Revision ID: f5e6f7a8b9c0
Revises: b9c8d7e6f5a4
Create Date: 2026-03-13 21:45:00.000000
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "f5e6f7a8b9c0"
down_revision = "b9c8d7e6f5a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "portfolio_aggregation_jobs",
        sa.Column("failure_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "portfolio_aggregation_jobs",
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("portfolio_aggregation_jobs", "attempt_count")
    op.drop_column("portfolio_aggregation_jobs", "failure_reason")
