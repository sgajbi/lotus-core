"""Add durable one-to-one position valuation calculation receipts.

Revision ID: c128b2c3d501
Revises: c127b2c3d500
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c128b2c3d501"
down_revision: str | Sequence[str] | None = "c127b2c3d500"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create complete authoritative or explicit legacy snapshot receipts."""

    op.create_table(
        "daily_position_valuation_receipts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("supportability", sa.String(), nullable=False),
        sa.Column("supportability_reasons", sa.JSON(), nullable=False),
        sa.Column("policy_id", sa.String(), nullable=True),
        sa.Column("policy_version", sa.Integer(), nullable=True),
        sa.Column("assignment_version", sa.Integer(), nullable=True),
        sa.Column("assignment_content_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "policy_assignment_source",
            sa.JSON(none_as_null=True),
            nullable=True,
        ),
        sa.Column("quote_basis", sa.String(), nullable=True),
        sa.Column("price_fact_version", sa.Integer(), nullable=True),
        sa.Column("price_fact_content_hash", sa.String(length=64), nullable=True),
        sa.Column("market_price_source", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("calculation_lineage", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("receipt_hash", sa.String(length=64), nullable=False),
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
        sa.CheckConstraint(
            "supportability IN ('SUPPORTED', 'LEGACY_UNSCOPED')",
            name="ck_daily_position_valuation_receipt_supportability",
        ),
        sa.CheckConstraint(
            "json_array_length(supportability_reasons) > 0",
            name="ck_daily_position_valuation_receipt_reasons_nonempty",
        ),
        sa.CheckConstraint(
            "("
            "supportability = 'SUPPORTED' "
            "AND policy_id IS NOT NULL AND btrim(policy_id) <> '' "
            "AND policy_version >= 1 AND assignment_version >= 1 "
            "AND assignment_content_hash IS NOT NULL "
            "AND policy_assignment_source IS NOT NULL "
            "AND quote_basis IS NOT NULL "
            "AND price_fact_version >= 1 AND price_fact_content_hash IS NOT NULL "
            "AND market_price_source IS NOT NULL AND calculation_lineage IS NOT NULL"
            ") OR ("
            "supportability = 'LEGACY_UNSCOPED' "
            "AND policy_id IS NULL AND policy_version IS NULL "
            "AND assignment_version IS NULL AND assignment_content_hash IS NULL "
            "AND policy_assignment_source IS NULL AND quote_basis IS NULL "
            "AND price_fact_version IS NULL AND price_fact_content_hash IS NULL "
            "AND market_price_source IS NULL AND calculation_lineage IS NULL"
            ")",
            name="ck_daily_position_valuation_receipt_evidence_complete",
        ),
        sa.CheckConstraint(
            "assignment_content_hash IS NULL OR assignment_content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_daily_position_valuation_receipt_assignment_hash",
        ),
        sa.CheckConstraint(
            "price_fact_content_hash IS NULL OR price_fact_content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_daily_position_valuation_receipt_price_hash",
        ),
        sa.CheckConstraint(
            "receipt_hash ~ '^[0-9a-f]{64}$'",
            name="ck_daily_position_valuation_receipt_hash",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["daily_position_snapshots.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "snapshot_id",
            name="uq_daily_position_valuation_receipt_snapshot",
        ),
    )
    op.create_index(
        "ix_daily_position_valuation_receipt_supportability_snapshot",
        "daily_position_valuation_receipts",
        ["supportability", "snapshot_id"],
    )


def downgrade() -> None:
    """Remove valuation receipts without changing snapshot calculations."""

    op.drop_index(
        "ix_daily_position_valuation_receipt_supportability_snapshot",
        table_name="daily_position_valuation_receipts",
    )
    op.drop_table("daily_position_valuation_receipts")
