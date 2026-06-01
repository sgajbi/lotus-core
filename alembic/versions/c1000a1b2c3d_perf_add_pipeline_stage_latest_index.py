"""Add latest pipeline stage support index.

Revision ID: c1000a1b2c3d
Revises: c0fff7a8b9c0
Create Date: 2026-06-01 00:45:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c1000a1b2c3d"
down_revision: str | Sequence[str] | None = "c0fff7a8b9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_pipeline_stage_state_port_stage_date_epoch_id",
        "pipeline_stage_state",
        [
            "portfolio_id",
            "stage_name",
            sa.text("business_date DESC"),
            sa.text("epoch DESC"),
            sa.text("id DESC"),
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_pipeline_stage_state_port_stage_date_epoch_id",
        table_name="pipeline_stage_state",
    )
