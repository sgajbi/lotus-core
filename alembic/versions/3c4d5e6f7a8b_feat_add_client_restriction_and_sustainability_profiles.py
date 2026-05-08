"""feat: add client restriction and sustainability source profiles

Revision ID: 3c4d5e6f7a8b
Revises: 2b3c4d5e6f7a
Create Date: 2026-05-08
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3c4d5e6f7a8b"
down_revision: Union[str, None] = "2b3c4d5e6f7a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "client_restriction_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("client_id", sa.String(), nullable=False),
        sa.Column("portfolio_id", sa.String(), nullable=False),
        sa.Column("mandate_id", sa.String(), nullable=True),
        sa.Column("restriction_scope", sa.String(), nullable=False),
        sa.Column("restriction_code", sa.String(), nullable=False),
        sa.Column("restriction_status", sa.String(), nullable=False),
        sa.Column("restriction_source", sa.String(), nullable=False),
        sa.Column("applies_to_buy", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("applies_to_sell", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("instrument_ids", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("asset_classes", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("issuer_ids", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("country_codes", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("restriction_version", sa.Integer(), server_default="1", nullable=False),
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
            "client_id",
            "portfolio_id",
            "restriction_code",
            "effective_from",
            "restriction_version",
            name="_client_restriction_profile_effective_uc",
        ),
    )
    for column_name in (
        "client_id",
        "portfolio_id",
        "mandate_id",
        "restriction_scope",
        "restriction_code",
        "restriction_status",
        "effective_from",
        "effective_to",
        "quality_status",
    ):
        op.create_index(
            f"ix_client_restriction_profiles_{column_name}",
            "client_restriction_profiles",
            [column_name],
        )
    op.create_index(
        "ix_client_restriction_profile_effective_window",
        "client_restriction_profiles",
        ["portfolio_id", "client_id", "effective_from", "effective_to"],
    )

    op.create_table(
        "sustainability_preference_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("client_id", sa.String(), nullable=False),
        sa.Column("portfolio_id", sa.String(), nullable=False),
        sa.Column("mandate_id", sa.String(), nullable=True),
        sa.Column("preference_framework", sa.String(), nullable=False),
        sa.Column("preference_code", sa.String(), nullable=False),
        sa.Column("preference_status", sa.String(), nullable=False),
        sa.Column("preference_source", sa.String(), nullable=False),
        sa.Column("minimum_allocation", sa.Numeric(18, 10), nullable=True),
        sa.Column("maximum_allocation", sa.Numeric(18, 10), nullable=True),
        sa.Column("applies_to_asset_classes", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("exclusion_codes", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("positive_tilt_codes", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("preference_version", sa.Integer(), server_default="1", nullable=False),
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
            "client_id",
            "portfolio_id",
            "preference_framework",
            "preference_code",
            "effective_from",
            "preference_version",
            name="_sustainability_preference_profile_effective_uc",
        ),
    )
    for column_name in (
        "client_id",
        "portfolio_id",
        "mandate_id",
        "preference_framework",
        "preference_code",
        "preference_status",
        "effective_from",
        "effective_to",
        "quality_status",
    ):
        op.create_index(
            f"ix_sustainability_preference_profiles_{column_name}",
            "sustainability_preference_profiles",
            [column_name],
        )
    op.create_index(
        "ix_sustainability_preference_effective_window",
        "sustainability_preference_profiles",
        ["portfolio_id", "client_id", "effective_from", "effective_to"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_sustainability_preference_effective_window",
        table_name="sustainability_preference_profiles",
    )
    for column_name in reversed(
        (
            "client_id",
            "portfolio_id",
            "mandate_id",
            "preference_framework",
            "preference_code",
            "preference_status",
            "effective_from",
            "effective_to",
            "quality_status",
        )
    ):
        op.drop_index(
            f"ix_sustainability_preference_profiles_{column_name}",
            table_name="sustainability_preference_profiles",
        )
    op.drop_table("sustainability_preference_profiles")

    op.drop_index(
        "ix_client_restriction_profile_effective_window",
        table_name="client_restriction_profiles",
    )
    for column_name in reversed(
        (
            "client_id",
            "portfolio_id",
            "mandate_id",
            "restriction_scope",
            "restriction_code",
            "restriction_status",
            "effective_from",
            "effective_to",
            "quality_status",
        )
    ):
        op.drop_index(
            f"ix_client_restriction_profiles_{column_name}",
            table_name="client_restriction_profiles",
        )
    op.drop_table("client_restriction_profiles")
