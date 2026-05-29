"""perf: add reconciliation run support index

Revision ID: c0e1f2a3b4c5
Revises: c0e0f1a2b3c4
Create Date: 2026-05-29 10:35:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c0e1f2a3b4c5"
down_revision: str | Sequence[str] | None = "c0e0f1a2b3c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_financial_reconciliation_runs_port_status_started_id",
        "financial_reconciliation_runs",
        ["portfolio_id", "status", sa.text("started_at DESC"), sa.text("id ASC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_financial_reconciliation_runs_port_status_started_id",
        table_name="financial_reconciliation_runs",
    )
