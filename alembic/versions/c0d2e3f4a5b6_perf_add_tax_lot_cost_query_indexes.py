"""perf add tax lot cost query indexes

Revision ID: c0d2e3f4a5b6
Revises: c0d1e2f3a4b5
Create Date: 2026-05-28 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c0d2e3f4a5b6"
down_revision: str | Sequence[str] | None = "c0d1e2f3a4b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_transaction_costs_transaction_id",
        "transaction_costs",
        ["transaction_id"],
        unique=False,
    )
    op.create_index(
        "ix_position_lot_port_norm_sec_acq_id",
        "position_lot_state",
        [
            "portfolio_id",
            sa.text("trim(security_id)"),
            "acquisition_date",
            "id",
        ],
        unique=False,
    )
    op.create_index(
        "ix_position_lot_port_acq_lot_id",
        "position_lot_state",
        ["portfolio_id", "acquisition_date", "lot_id"],
        unique=False,
    )
    op.create_index(
        "ix_accrued_offset_port_norm_sec_id",
        "accrued_income_offset_state",
        ["portfolio_id", sa.text("trim(security_id)"), "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_accrued_offset_port_norm_sec_id", table_name="accrued_income_offset_state")
    op.drop_index("ix_position_lot_port_acq_lot_id", table_name="position_lot_state")
    op.drop_index("ix_position_lot_port_norm_sec_acq_id", table_name="position_lot_state")
    op.drop_index("ix_transaction_costs_transaction_id", table_name="transaction_costs")
