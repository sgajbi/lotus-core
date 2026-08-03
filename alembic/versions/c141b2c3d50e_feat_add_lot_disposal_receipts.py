"""Add immutable versioned lot-disposal receipts and allocations.

Revision ID: c141b2c3d50e
Revises: c140b2c3d50d
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c141b2c3d50e"
down_revision: str | Sequence[str] | None = "c140b2c3d50d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create append-only receipt headers before their ordered children."""

    op.create_table(
        "lot_disposal_receipts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("receipt_id", sa.String(length=96), nullable=False),
        sa.Column("receipt_version", sa.Integer(), nullable=False),
        sa.Column("disposal_transaction_id", sa.String(), nullable=False),
        sa.Column("portfolio_id", sa.String(), nullable=False),
        sa.Column("instrument_id", sa.String(), nullable=False),
        sa.Column("security_id", sa.String(), nullable=False),
        sa.Column("disposal_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("transaction_type", sa.String(), nullable=False),
        sa.Column("cost_basis_method", sa.String(), nullable=False),
        sa.Column("calculation_policy_id", sa.String(), nullable=True),
        sa.Column("calculation_policy_version", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("void_reason", sa.String(), nullable=True),
        sa.Column("consumed_quantity", sa.Numeric(18, 10), nullable=False),
        sa.Column("consumed_cost_local", sa.Numeric(18, 10), nullable=False),
        sa.Column("consumed_cost_base", sa.Numeric(18, 10), nullable=False),
        sa.Column("allocation_count", sa.Integer(), nullable=False),
        sa.Column(
            "transaction_calculation_lineage",
            postgresql.JSONB(none_as_null=True),
            nullable=False,
        ),
        sa.Column(
            "disposal_calculation_lineage",
            postgresql.JSONB(none_as_null=True),
            nullable=True,
        ),
        sa.Column("semantic_content_hash", sa.String(length=64), nullable=False),
        sa.Column("previous_receipt_content_hash", sa.String(length=64), nullable=True),
        sa.Column("receipt_content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "receipt_version >= 1 AND allocation_count >= 0",
            name="ck_lot_disposal_receipt_counts",
        ),
        sa.CheckConstraint(
            "receipt_id = btrim(receipt_id) AND receipt_id <> '' "
            "AND disposal_transaction_id = btrim(disposal_transaction_id) "
            "AND disposal_transaction_id <> '' "
            "AND portfolio_id = btrim(portfolio_id) AND portfolio_id <> '' "
            "AND instrument_id = btrim(instrument_id) AND instrument_id <> '' "
            "AND security_id = btrim(security_id) AND security_id <> '' "
            "AND transaction_type = btrim(transaction_type) AND transaction_type <> ''",
            name="ck_lot_disposal_receipt_identity",
        ),
        sa.CheckConstraint(
            "cost_basis_method IN ('FIFO', 'AVCO')",
            name="ck_lot_disposal_receipt_method",
        ),
        sa.CheckConstraint(
            "(calculation_policy_id IS NULL AND calculation_policy_version IS NULL) "
            "OR (calculation_policy_id = btrim(calculation_policy_id) "
            "AND calculation_policy_id <> '' "
            "AND calculation_policy_version = btrim(calculation_policy_version) "
            "AND calculation_policy_version <> '')",
            name="ck_lot_disposal_receipt_policy",
        ),
        sa.CheckConstraint(
            "CAST(consumed_quantity AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
            "AND CAST(consumed_cost_local AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
            "AND CAST(consumed_cost_base AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
            name="ck_lot_disposal_receipt_amounts_finite",
        ),
        sa.CheckConstraint(
            "consumed_quantity >= 0 AND consumed_cost_local >= 0 AND consumed_cost_base >= 0",
            name="ck_lot_disposal_receipt_amounts_nonnegative",
        ),
        sa.CheckConstraint(
            "(status = 'ACTIVE' AND void_reason IS NULL "
            "AND consumed_quantity > 0 AND allocation_count > 0 "
            "AND disposal_calculation_lineage IS NOT NULL) "
            "OR (status = 'VOIDED' AND void_reason = btrim(void_reason) "
            "AND void_reason <> '' AND consumed_quantity = 0 "
            "AND consumed_cost_local = 0 AND consumed_cost_base = 0 "
            "AND allocation_count = 0 AND disposal_calculation_lineage IS NULL)",
            name="ck_lot_disposal_receipt_lifecycle",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(transaction_calculation_lineage) = 'object' "
            "AND (disposal_calculation_lineage IS NULL "
            "OR jsonb_typeof(disposal_calculation_lineage) = 'object')",
            name="ck_lot_disposal_receipt_lineage",
        ),
        sa.CheckConstraint(
            "semantic_content_hash ~ '^[0-9a-f]{64}$' "
            "AND receipt_content_hash ~ '^[0-9a-f]{64}$' "
            "AND (previous_receipt_content_hash IS NULL "
            "OR previous_receipt_content_hash ~ '^[0-9a-f]{64}$')",
            name="ck_lot_disposal_receipt_hashes",
        ),
        sa.CheckConstraint(
            "(receipt_version = 1 AND previous_receipt_content_hash IS NULL) "
            "OR (receipt_version > 1 AND previous_receipt_content_hash IS NOT NULL)",
            name="ck_lot_disposal_receipt_chain",
        ),
        sa.ForeignKeyConstraint(
            ["disposal_transaction_id"],
            ["transactions.transaction_id"],
            name="fk_lot_disposal_receipt_transaction",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolios.portfolio_id"],
            name="fk_lot_disposal_receipt_portfolio",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["security_id"],
            ["instruments.security_id"],
            name="fk_lot_disposal_receipt_security",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_lot_disposal_receipts"),
        sa.UniqueConstraint(
            "receipt_id",
            "receipt_version",
            name="uq_lot_disposal_receipt_version",
        ),
        sa.UniqueConstraint(
            "disposal_transaction_id",
            "receipt_version",
            name="uq_lot_disposal_transaction_version",
        ),
        sa.UniqueConstraint(
            "receipt_id",
            "receipt_version",
            "portfolio_id",
            "security_id",
            name="uq_lot_disposal_receipt_scope_version",
        ),
    )
    op.create_index(
        "ix_lot_disposal_receipt_scope_time",
        "lot_disposal_receipts",
        [
            "portfolio_id",
            "security_id",
            sa.text("disposal_timestamp DESC"),
            sa.text("receipt_version DESC"),
        ],
    )
    op.create_index(
        "ix_lot_disposal_receipt_tx_version",
        "lot_disposal_receipts",
        ["disposal_transaction_id", sa.text("receipt_version DESC")],
    )

    op.create_table(
        "lot_disposal_allocations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("receipt_id", sa.String(length=96), nullable=False),
        sa.Column("receipt_version", sa.Integer(), nullable=False),
        sa.Column("portfolio_id", sa.String(), nullable=False),
        sa.Column("security_id", sa.String(), nullable=False),
        sa.Column("allocation_ordinal", sa.Integer(), nullable=False),
        sa.Column("source_lot_id", sa.String(), nullable=False),
        sa.Column("source_transaction_id", sa.String(), nullable=False),
        sa.Column("source_acquisition_date", sa.Date(), nullable=False),
        sa.Column("consumed_quantity", sa.Numeric(18, 10), nullable=False),
        sa.Column("consumed_cost_local", sa.Numeric(18, 10), nullable=False),
        sa.Column("consumed_cost_base", sa.Numeric(18, 10), nullable=False),
        sa.Column("allocation_content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "receipt_version >= 1 AND allocation_ordinal >= 1",
            name="ck_lot_disposal_allocation_identity",
        ),
        sa.CheckConstraint(
            "receipt_id = btrim(receipt_id) AND receipt_id <> '' "
            "AND portfolio_id = btrim(portfolio_id) AND portfolio_id <> '' "
            "AND security_id = btrim(security_id) AND security_id <> '' "
            "AND source_lot_id = btrim(source_lot_id) AND source_lot_id <> '' "
            "AND source_transaction_id = btrim(source_transaction_id) "
            "AND source_transaction_id <> ''",
            name="ck_lot_disposal_allocation_scope",
        ),
        sa.CheckConstraint(
            "CAST(consumed_quantity AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
            "AND CAST(consumed_cost_local AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity') "
            "AND CAST(consumed_cost_base AS TEXT) NOT IN ('NaN', 'Infinity', '-Infinity')",
            name="ck_lot_disposal_allocation_amounts_finite",
        ),
        sa.CheckConstraint(
            "consumed_quantity > 0 AND consumed_cost_local >= 0 AND consumed_cost_base >= 0",
            name="ck_lot_disposal_allocation_amounts",
        ),
        sa.CheckConstraint(
            "allocation_content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_lot_disposal_allocation_hash",
        ),
        sa.ForeignKeyConstraint(
            ["receipt_id", "receipt_version", "portfolio_id", "security_id"],
            [
                "lot_disposal_receipts.receipt_id",
                "lot_disposal_receipts.receipt_version",
                "lot_disposal_receipts.portfolio_id",
                "lot_disposal_receipts.security_id",
            ],
            name="fk_lot_disposal_allocation_receipt",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_transaction_id"],
            ["transactions.transaction_id"],
            name="fk_lot_disposal_allocation_source_tx",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_lot_id", "portfolio_id", "security_id"],
            [
                "position_lot_state.lot_id",
                "position_lot_state.portfolio_id",
                "position_lot_state.security_id",
            ],
            name="fk_lot_disposal_allocation_lot_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_lot_disposal_allocations"),
        sa.UniqueConstraint(
            "receipt_id",
            "receipt_version",
            "allocation_ordinal",
            name="uq_lot_disposal_allocation_ordinal",
        ),
        sa.UniqueConstraint(
            "receipt_id",
            "receipt_version",
            "source_lot_id",
            name="uq_lot_disposal_allocation_source_lot",
        ),
    )
    op.create_index(
        "ix_lot_disposal_allocation_source",
        "lot_disposal_allocations",
        ["portfolio_id", "security_id", "source_lot_id", "source_acquisition_date"],
    )


def downgrade() -> None:
    """Remove child allocations before their receipt headers."""

    op.drop_index(
        "ix_lot_disposal_allocation_source",
        table_name="lot_disposal_allocations",
    )
    op.drop_table("lot_disposal_allocations")
    op.drop_index(
        "ix_lot_disposal_receipt_tx_version",
        table_name="lot_disposal_receipts",
    )
    op.drop_index(
        "ix_lot_disposal_receipt_scope_time",
        table_name="lot_disposal_receipts",
    )
    op.drop_table("lot_disposal_receipts")
