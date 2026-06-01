"""Add DPM model source-data support indexes.

Revision ID: c0f2a3b4c5d6
Revises: c0f1a2b3c4d5
Create Date: 2026-05-31 10:55:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "c0f2a3b4c5d6"
down_revision = "c0f1a2b3c4d5"
branch_labels = None
depends_on = None


MODEL_DEFINITION_INDEX = "ix_model_port_def_approved_eff_order"
MODEL_TARGET_INDEX = "ix_model_port_tgt_active_eff_order"


def upgrade() -> None:
    op.execute(
        "UPDATE model_portfolio_definitions "
        "SET approval_status = lower(trim(approval_status)) "
        "WHERE approval_status IS NOT NULL"
    )
    op.execute(
        "UPDATE model_portfolio_targets "
        "SET target_status = lower(trim(target_status)) "
        "WHERE target_status IS NOT NULL"
    )
    op.create_index(
        MODEL_DEFINITION_INDEX,
        "model_portfolio_definitions",
        [
            "model_portfolio_id",
            sa.text("effective_from DESC"),
            "effective_to",
            sa.text("approved_at DESC"),
            sa.text("updated_at DESC"),
        ],
        unique=False,
        postgresql_where=sa.text("approval_status = 'approved'"),
    )
    op.create_index(
        MODEL_TARGET_INDEX,
        "model_portfolio_targets",
        [
            "model_portfolio_id",
            "model_portfolio_version",
            "instrument_id",
            sa.text("effective_from DESC"),
            "effective_to",
        ],
        unique=False,
        postgresql_where=sa.text("target_status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index(MODEL_TARGET_INDEX, table_name="model_portfolio_targets")
    op.drop_index(MODEL_DEFINITION_INDEX, table_name="model_portfolio_definitions")
    # Model lifecycle status canonicalization is data cleanup and is intentionally irreversible.
