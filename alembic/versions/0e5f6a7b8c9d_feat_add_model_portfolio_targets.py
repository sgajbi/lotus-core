"""feat: add model portfolio target source tables

Revision ID: 0e5f6a7b8c9d
Revises: 0d4e5f6a7b8c
Create Date: 2026-05-02 10:15:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0e5f6a7b8c9d"
down_revision: Union[str, None] = "0d4e5f6a7b8c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "model_portfolio_definitions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("model_portfolio_id", sa.String(), nullable=False),
        sa.Column("model_portfolio_version", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("base_currency", sa.String(length=3), nullable=False),
        sa.Column("risk_profile", sa.String(), nullable=False),
        sa.Column("mandate_type", sa.String(), nullable=False),
        sa.Column("rebalance_frequency", sa.String(), nullable=True),
        sa.Column("approval_status", sa.String(), server_default="approved", nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("source_system", sa.String(), nullable=True),
        sa.Column("source_record_id", sa.String(), nullable=True),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quality_status", sa.String(), server_default="accepted", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "model_portfolio_id",
            "model_portfolio_version",
            "effective_from",
            name="_model_portfolio_definition_version_effective_uc",
        ),
    )
    op.create_index(
        "ix_model_portfolio_definitions_model_portfolio_id",
        "model_portfolio_definitions",
        ["model_portfolio_id"],
    )
    op.create_index(
        "ix_model_portfolio_definitions_model_portfolio_version",
        "model_portfolio_definitions",
        ["model_portfolio_version"],
    )
    op.create_index(
        "ix_model_portfolio_definitions_approval_status",
        "model_portfolio_definitions",
        ["approval_status"],
    )
    op.create_index(
        "ix_model_portfolio_definition_effective_window",
        "model_portfolio_definitions",
        ["model_portfolio_id", "effective_from", "effective_to"],
    )

    op.create_table(
        "model_portfolio_targets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("model_portfolio_id", sa.String(), nullable=False),
        sa.Column("model_portfolio_version", sa.String(), nullable=False),
        sa.Column("instrument_id", sa.String(), nullable=False),
        sa.Column("target_weight", sa.Numeric(18, 10), nullable=False),
        sa.Column("min_weight", sa.Numeric(18, 10), nullable=True),
        sa.Column("max_weight", sa.Numeric(18, 10), nullable=True),
        sa.Column("target_status", sa.String(), server_default="active", nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("source_system", sa.String(), nullable=True),
        sa.Column("source_record_id", sa.String(), nullable=True),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quality_status", sa.String(), server_default="accepted", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "model_portfolio_id",
            "model_portfolio_version",
            "instrument_id",
            "effective_from",
            name="_model_portfolio_target_instrument_effective_uc",
        ),
    )
    op.create_index(
        "ix_model_portfolio_targets_model_portfolio_id",
        "model_portfolio_targets",
        ["model_portfolio_id"],
    )
    op.create_index(
        "ix_model_portfolio_targets_model_portfolio_version",
        "model_portfolio_targets",
        ["model_portfolio_version"],
    )
    op.create_index(
        "ix_model_portfolio_targets_instrument_id",
        "model_portfolio_targets",
        ["instrument_id"],
    )
    op.create_index(
        "ix_model_portfolio_targets_target_status",
        "model_portfolio_targets",
        ["target_status"],
    )
    op.create_index(
        "ix_model_portfolio_target_effective_window",
        "model_portfolio_targets",
        ["model_portfolio_id", "model_portfolio_version", "effective_from", "effective_to"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_model_portfolio_target_effective_window",
        table_name="model_portfolio_targets",
    )
    op.drop_index(
        "ix_model_portfolio_targets_target_status",
        table_name="model_portfolio_targets",
    )
    op.drop_index(
        "ix_model_portfolio_targets_instrument_id",
        table_name="model_portfolio_targets",
    )
    op.drop_index(
        "ix_model_portfolio_targets_model_portfolio_version",
        table_name="model_portfolio_targets",
    )
    op.drop_index(
        "ix_model_portfolio_targets_model_portfolio_id",
        table_name="model_portfolio_targets",
    )
    op.drop_table("model_portfolio_targets")
    op.drop_index(
        "ix_model_portfolio_definition_effective_window",
        table_name="model_portfolio_definitions",
    )
    op.drop_index(
        "ix_model_portfolio_definitions_approval_status",
        table_name="model_portfolio_definitions",
    )
    op.drop_index(
        "ix_model_portfolio_definitions_model_portfolio_version",
        table_name="model_portfolio_definitions",
    )
    op.drop_index(
        "ix_model_portfolio_definitions_model_portfolio_id",
        table_name="model_portfolio_definitions",
    )
    op.drop_table("model_portfolio_definitions")
