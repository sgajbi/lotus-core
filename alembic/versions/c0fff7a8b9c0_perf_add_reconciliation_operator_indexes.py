"""Add reconciliation operator support indexes.

Revision ID: c0fff7a8b9c0
Revises: c0fee6f7a8c0
Create Date: 2026-06-01 00:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c0fff7a8b9c0"
down_revision: str | Sequence[str] | None = "c0fee6f7a8c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_fin_recon_runs_port_corr_started_id",
        "financial_reconciliation_runs",
        ["portfolio_id", "correlation_id", sa.text("started_at DESC"), sa.text("id ASC")],
        unique=False,
    )
    op.create_index(
        "ix_fin_recon_runs_port_req_by_started_id",
        "financial_reconciliation_runs",
        ["portfolio_id", "requested_by", sa.text("started_at DESC"), sa.text("id ASC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_fin_recon_runs_port_req_by_started_id",
        table_name="financial_reconciliation_runs",
    )
    op.drop_index(
        "ix_fin_recon_runs_port_corr_started_id",
        table_name="financial_reconciliation_runs",
    )
