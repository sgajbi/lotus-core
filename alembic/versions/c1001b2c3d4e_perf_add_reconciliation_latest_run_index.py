"""Add latest reconciliation run support index.

Revision ID: c1001b2c3d4e
Revises: c1000a1b2c3d
Create Date: 2026-06-01 01:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c1001b2c3d4e"
down_revision: str | Sequence[str] | None = "c1000a1b2c3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_fin_recon_runs_port_date_epoch_started_id",
        "financial_reconciliation_runs",
        [
            "portfolio_id",
            "business_date",
            "epoch",
            sa.text("started_at DESC"),
            sa.text("id DESC"),
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_fin_recon_runs_port_date_epoch_started_id",
        table_name="financial_reconciliation_runs",
    )
