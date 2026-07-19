"""Persist aggregation revision lineage for reconciliation controls.

Revision ID: c117b2c3d4f6
Revises: c116b2c3d4f5
Create Date: 2026-07-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c117b2c3d4f6"
down_revision: str | None = "c116b2c3d4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add revision-aware reconciliation execution and control evidence."""

    op.add_column(
        "pipeline_stage_state",
        sa.Column(
            "aggregation_revision",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_pipeline_stage_aggregation_revision_nonnegative",
        "pipeline_stage_state",
        "aggregation_revision >= 0",
    )
    op.add_column(
        "financial_reconciliation_runs",
        sa.Column("aggregation_revision", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_fin_recon_aggregation_revision_nonnegative",
        "financial_reconciliation_runs",
        "aggregation_revision IS NULL OR aggregation_revision >= 0",
    )
    op.create_index(
        "ix_fin_recon_scope_revision_type",
        "financial_reconciliation_runs",
        [
            "portfolio_id",
            "business_date",
            "epoch",
            "aggregation_revision",
            "reconciliation_type",
        ],
    )


def downgrade() -> None:
    """Remove aggregation revision lineage from reconciliation persistence."""

    op.drop_index(
        "ix_fin_recon_scope_revision_type",
        table_name="financial_reconciliation_runs",
    )
    op.drop_constraint(
        "ck_fin_recon_aggregation_revision_nonnegative",
        "financial_reconciliation_runs",
        type_="check",
    )
    op.drop_column("financial_reconciliation_runs", "aggregation_revision")
    op.drop_constraint(
        "ck_pipeline_stage_aggregation_revision_nonnegative",
        "pipeline_stage_state",
        type_="check",
    )
    op.drop_column("pipeline_stage_state", "aggregation_revision")
