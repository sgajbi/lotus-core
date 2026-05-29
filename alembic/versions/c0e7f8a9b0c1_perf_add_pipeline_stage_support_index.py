"""Add pipeline stage support index.

Revision ID: c0e7f8a9b0c1
Revises: c0e6f7a8b9c0
Create Date: 2026-05-29 09:10:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "c0e7f8a9b0c1"
down_revision = "c0e6f7a8b9c0"
branch_labels = None
depends_on = None


INDEX_NAME = "ix_pipeline_stage_state_port_status_date_stage_epoch_updated_id"


def upgrade() -> None:
    op.execute(
        "UPDATE pipeline_stage_state SET status = upper(trim(status)) WHERE status IS NOT NULL"
    )
    op.create_index(
        INDEX_NAME,
        "pipeline_stage_state",
        [
            "portfolio_id",
            "status",
            sa.text("business_date DESC"),
            "stage_name",
            sa.text("epoch DESC"),
            sa.text("updated_at DESC"),
            sa.text("id ASC"),
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="pipeline_stage_state")
    # Status canonicalization is data cleanup and is intentionally irreversible.
