"""perf add timeseries cashflow api indexes

Revision ID: c0d1e2f3a4b5
Revises: b0c1d2e3f4a6
Create Date: 2026-05-28 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c0d1e2f3a4b5"
down_revision: str | Sequence[str] | None = "b0c1d2e3f4a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_cashflows_port_norm_sec_date_epoch",
        "cashflows",
        [
            "portfolio_id",
            sa.text("trim(security_id)"),
            "cashflow_date",
            sa.text("epoch DESC"),
        ],
        unique=False,
    )
    op.create_index(
        "ix_pos_ts_port_date_norm_sec_epoch",
        "position_timeseries",
        [
            "portfolio_id",
            "date",
            sa.text("trim(security_id)"),
            sa.text("epoch DESC"),
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_pos_ts_port_date_norm_sec_epoch", table_name="position_timeseries")
    op.drop_index("ix_cashflows_port_norm_sec_date_epoch", table_name="cashflows")
