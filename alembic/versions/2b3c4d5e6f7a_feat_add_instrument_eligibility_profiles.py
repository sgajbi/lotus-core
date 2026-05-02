"""feat: add instrument eligibility source table

Revision ID: 2b3c4d5e6f7a
Revises: 1a2b3c4d5e6f
Create Date: 2026-05-02
"""

from alembic import op
import sqlalchemy as sa


revision = "2b3c4d5e6f7a"
down_revision = "1a2b3c4d5e6f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "instrument_eligibility_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("security_id", sa.String(), nullable=False),
        sa.Column("eligibility_status", sa.String(), nullable=False),
        sa.Column("product_shelf_status", sa.String(), nullable=False),
        sa.Column("buy_allowed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("sell_allowed", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("restriction_reason_codes", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("restriction_rationale", sa.Text(), nullable=True),
        sa.Column("settlement_days", sa.Integer(), server_default="2", nullable=False),
        sa.Column("settlement_calendar_id", sa.String(), server_default="GLOBAL", nullable=False),
        sa.Column("liquidity_tier", sa.String(), nullable=True),
        sa.Column("issuer_id", sa.String(), nullable=True),
        sa.Column("issuer_name", sa.String(), nullable=True),
        sa.Column("ultimate_parent_issuer_id", sa.String(), nullable=True),
        sa.Column("ultimate_parent_issuer_name", sa.String(), nullable=True),
        sa.Column("asset_class", sa.String(), nullable=True),
        sa.Column("country_of_risk", sa.String(), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("eligibility_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("source_system", sa.String(), nullable=True),
        sa.Column("source_record_id", sa.String(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quality_status", sa.String(), server_default="accepted", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["security_id"], ["instruments.security_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "security_id",
            "effective_from",
            "eligibility_version",
            name="_instrument_eligibility_profile_uc",
        ),
    )
    op.create_index(
        "ix_instrument_eligibility_profiles_security_id",
        "instrument_eligibility_profiles",
        ["security_id"],
    )
    op.create_index(
        "ix_instrument_eligibility_profiles_eligibility_status",
        "instrument_eligibility_profiles",
        ["eligibility_status"],
    )
    op.create_index(
        "ix_instrument_eligibility_profiles_product_shelf_status",
        "instrument_eligibility_profiles",
        ["product_shelf_status"],
    )
    op.create_index(
        "ix_instrument_eligibility_profiles_issuer_id",
        "instrument_eligibility_profiles",
        ["issuer_id"],
    )
    op.create_index(
        "ix_instrument_eligibility_profiles_ultimate_parent_issuer_id",
        "instrument_eligibility_profiles",
        ["ultimate_parent_issuer_id"],
    )
    op.create_index(
        "ix_instrument_eligibility_profiles_effective_from",
        "instrument_eligibility_profiles",
        ["effective_from"],
    )
    op.create_index(
        "ix_instrument_eligibility_profiles_effective_to",
        "instrument_eligibility_profiles",
        ["effective_to"],
    )
    op.create_index(
        "ix_instrument_eligibility_profiles_quality_status",
        "instrument_eligibility_profiles",
        ["quality_status"],
    )
    op.create_index(
        "ix_instrument_eligibility_effective_window",
        "instrument_eligibility_profiles",
        ["security_id", "effective_from", "effective_to"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_instrument_eligibility_effective_window",
        table_name="instrument_eligibility_profiles",
    )
    op.drop_index(
        "ix_instrument_eligibility_profiles_quality_status",
        table_name="instrument_eligibility_profiles",
    )
    op.drop_index(
        "ix_instrument_eligibility_profiles_effective_to",
        table_name="instrument_eligibility_profiles",
    )
    op.drop_index(
        "ix_instrument_eligibility_profiles_effective_from",
        table_name="instrument_eligibility_profiles",
    )
    op.drop_index(
        "ix_instrument_eligibility_profiles_ultimate_parent_issuer_id",
        table_name="instrument_eligibility_profiles",
    )
    op.drop_index(
        "ix_instrument_eligibility_profiles_issuer_id",
        table_name="instrument_eligibility_profiles",
    )
    op.drop_index(
        "ix_instrument_eligibility_profiles_product_shelf_status",
        table_name="instrument_eligibility_profiles",
    )
    op.drop_index(
        "ix_instrument_eligibility_profiles_eligibility_status",
        table_name="instrument_eligibility_profiles",
    )
    op.drop_index(
        "ix_instrument_eligibility_profiles_security_id",
        table_name="instrument_eligibility_profiles",
    )
    op.drop_table("instrument_eligibility_profiles")
