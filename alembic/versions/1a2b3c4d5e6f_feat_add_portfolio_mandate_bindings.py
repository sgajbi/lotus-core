"""feat: add portfolio mandate binding source table

Revision ID: 1a2b3c4d5e6f
Revises: 0e5f6a7b8c9d
Create Date: 2026-05-02 14:20:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "1a2b3c4d5e6f"
down_revision: Union[str, None] = "0e5f6a7b8c9d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "portfolio_mandate_bindings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("portfolio_id", sa.String(), nullable=False),
        sa.Column("mandate_id", sa.String(), nullable=False),
        sa.Column("client_id", sa.String(), nullable=False),
        sa.Column("mandate_type", sa.String(), nullable=False),
        sa.Column("discretionary_authority_status", sa.String(), nullable=False),
        sa.Column("booking_center_code", sa.String(), nullable=False),
        sa.Column("jurisdiction_code", sa.String(), nullable=False),
        sa.Column("model_portfolio_id", sa.String(), nullable=False),
        sa.Column("policy_pack_id", sa.String(), nullable=True),
        sa.Column("risk_profile", sa.String(), nullable=False),
        sa.Column("investment_horizon", sa.String(), nullable=False),
        sa.Column("leverage_allowed", sa.Boolean(), server_default="f", nullable=False),
        sa.Column("tax_awareness_allowed", sa.Boolean(), server_default="f", nullable=False),
        sa.Column(
            "settlement_awareness_required",
            sa.Boolean(),
            server_default="f",
            nullable=False,
        ),
        sa.Column("rebalance_frequency", sa.String(), nullable=False),
        sa.Column("rebalance_bands", sa.JSON(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("binding_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("source_system", sa.String(), nullable=True),
        sa.Column("source_record_id", sa.String(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.portfolio_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "portfolio_id",
            "mandate_id",
            "effective_from",
            "binding_version",
            name="_portfolio_mandate_binding_effective_uc",
        ),
    )
    for column_name in (
        "portfolio_id",
        "mandate_id",
        "client_id",
        "mandate_type",
        "discretionary_authority_status",
        "booking_center_code",
        "jurisdiction_code",
        "model_portfolio_id",
        "policy_pack_id",
        "effective_from",
        "effective_to",
        "quality_status",
    ):
        op.create_index(
            f"ix_portfolio_mandate_bindings_{column_name}",
            "portfolio_mandate_bindings",
            [column_name],
        )
    op.create_index(
        "ix_portfolio_mandate_binding_effective_window",
        "portfolio_mandate_bindings",
        ["portfolio_id", "effective_from", "effective_to"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_portfolio_mandate_binding_effective_window",
        table_name="portfolio_mandate_bindings",
    )
    for column_name in reversed(
        (
            "portfolio_id",
            "mandate_id",
            "client_id",
            "mandate_type",
            "discretionary_authority_status",
            "booking_center_code",
            "jurisdiction_code",
            "model_portfolio_id",
            "policy_pack_id",
            "effective_from",
            "effective_to",
            "quality_status",
        )
    ):
        op.drop_index(
            f"ix_portfolio_mandate_bindings_{column_name}",
            table_name="portfolio_mandate_bindings",
        )
    op.drop_table("portfolio_mandate_bindings")
