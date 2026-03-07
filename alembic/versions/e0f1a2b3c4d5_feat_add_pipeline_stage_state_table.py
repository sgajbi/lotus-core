"""feat: add pipeline stage state table for orchestrator gates

Revision ID: e0f1a2b3c4d5
Revises: d8e9f0a1b2c3
Create Date: 2026-03-07 22:45:00
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e0f1a2b3c4d5"
down_revision: Union[str, None] = "d8e9f0a1b2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipeline_stage_state",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("stage_name", sa.String(), nullable=False),
        sa.Column("transaction_id", sa.String(), nullable=False),
        sa.Column("portfolio_id", sa.String(), nullable=False),
        sa.Column("security_id", sa.String(), nullable=True),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("epoch", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(), nullable=False, server_default="PENDING"),
        sa.Column("cost_event_seen", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("cashflow_event_seen", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("ready_emitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_source_event_type", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "stage_name",
            "transaction_id",
            "epoch",
            name="_pipeline_stage_state_stage_tx_epoch_uc",
        ),
    )

    op.create_index(
        "ix_pipeline_stage_state_portfolio_date_stage_status",
        "pipeline_stage_state",
        ["portfolio_id", "business_date", "stage_name", "status"],
        unique=False,
    )
    op.create_index(
        "ix_pipeline_stage_state_stage_name",
        "pipeline_stage_state",
        ["stage_name"],
        unique=False,
    )
    op.create_index(
        "ix_pipeline_stage_state_transaction_id",
        "pipeline_stage_state",
        ["transaction_id"],
        unique=False,
    )
    op.create_index(
        "ix_pipeline_stage_state_portfolio_id",
        "pipeline_stage_state",
        ["portfolio_id"],
        unique=False,
    )
    op.create_index(
        "ix_pipeline_stage_state_security_id",
        "pipeline_stage_state",
        ["security_id"],
        unique=False,
    )
    op.create_index(
        "ix_pipeline_stage_state_business_date",
        "pipeline_stage_state",
        ["business_date"],
        unique=False,
    )
    op.create_index(
        "ix_pipeline_stage_state_epoch",
        "pipeline_stage_state",
        ["epoch"],
        unique=False,
    )
    op.create_index(
        "ix_pipeline_stage_state_status",
        "pipeline_stage_state",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_pipeline_stage_state_status", table_name="pipeline_stage_state")
    op.drop_index("ix_pipeline_stage_state_epoch", table_name="pipeline_stage_state")
    op.drop_index("ix_pipeline_stage_state_business_date", table_name="pipeline_stage_state")
    op.drop_index("ix_pipeline_stage_state_security_id", table_name="pipeline_stage_state")
    op.drop_index("ix_pipeline_stage_state_portfolio_id", table_name="pipeline_stage_state")
    op.drop_index("ix_pipeline_stage_state_transaction_id", table_name="pipeline_stage_state")
    op.drop_index("ix_pipeline_stage_state_stage_name", table_name="pipeline_stage_state")
    op.drop_index(
        "ix_pipeline_stage_state_portfolio_date_stage_status", table_name="pipeline_stage_state"
    )
    op.drop_table("pipeline_stage_state")
