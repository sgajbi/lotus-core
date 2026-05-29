"""perf: add reconciliation run list index

Revision ID: c0e3f4a5b6c7
Revises: c0e2f3a4b5c6
Create Date: 2026-05-29 11:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c0e3f4a5b6c7"
down_revision: str | Sequence[str] | None = "c0e2f3a4b5c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_financial_reconciliation_runs_port_type_started_id",
        "financial_reconciliation_runs",
        ["portfolio_id", "reconciliation_type", sa.text("started_at DESC"), sa.text("id DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_financial_reconciliation_runs_port_type_started_id",
        table_name="financial_reconciliation_runs",
    )
