"""Add discriminated destinations to lot-disposal receipt headers.

Revision ID: c147b2c3d514
Revises: c146b2c3d513
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c147b2c3d514"
down_revision: str | Sequence[str] | None = "c146b2c3d513"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "lot_disposal_receipts"


def upgrade() -> None:
    """Add one optional destination discriminator without rewriting legacy receipts."""

    for column in (
        sa.Column("destination_type", sa.String(), nullable=True),
        sa.Column("target_transaction_id", sa.String(), nullable=True),
        sa.Column("target_lot_id", sa.String(), nullable=True),
        sa.Column("target_instrument_id", sa.String(), nullable=True),
        sa.Column("external_destination_reference", sa.String(), nullable=True),
    ):
        op.add_column(_TABLE, column)
    op.create_check_constraint(
        "ck_lot_disposal_receipt_destination",
        _TABLE,
        "(destination_type IS NULL AND target_transaction_id IS NULL "
        "AND target_lot_id IS NULL AND target_instrument_id IS NULL "
        "AND external_destination_reference IS NULL) OR "
        "(destination_type = 'INTERNAL_LOT' "
        "AND target_transaction_id = btrim(target_transaction_id) "
        "AND target_transaction_id <> '' "
        "AND target_lot_id = 'LOT-' || target_transaction_id "
        "AND target_instrument_id = btrim(target_instrument_id) "
        "AND target_instrument_id <> '' AND external_destination_reference IS NULL) OR "
        "(destination_type = 'EXTERNAL_TRANSFER' "
        "AND external_destination_reference = btrim(external_destination_reference) "
        "AND external_destination_reference <> '' AND target_transaction_id IS NULL "
        "AND target_lot_id IS NULL AND target_instrument_id IS NULL)",
    )
    op.create_index(
        "ix_lot_disposal_receipt_target_tx_version",
        _TABLE,
        ["portfolio_id", "target_transaction_id", sa.text("receipt_version DESC")],
    )
    op.create_index(
        "ix_lot_disposal_receipt_external_destination",
        _TABLE,
        ["portfolio_id", "external_destination_reference"],
    )


def downgrade() -> None:
    """Remove destination metadata while retaining receipt economics."""

    op.drop_index("ix_lot_disposal_receipt_external_destination", table_name=_TABLE)
    op.drop_index("ix_lot_disposal_receipt_target_tx_version", table_name=_TABLE)
    op.drop_constraint("ck_lot_disposal_receipt_destination", _TABLE, type_="check")
    for column_name in (
        "external_destination_reference",
        "target_instrument_id",
        "target_lot_id",
        "target_transaction_id",
        "destination_type",
    ):
        op.drop_column(_TABLE, column_name)
