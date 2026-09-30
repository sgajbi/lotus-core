"""Persist transaction FX rate authority provenance.

Revision ID: c175b2c3d536
Revises: c174b2c3d535
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c175b2c3d536"
down_revision: str | Sequence[str] | None = "c174b2c3d535"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add provenance without pretending legacy calculated rates were source-booked."""

    op.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
    op.add_column(
        "transactions",
        sa.Column("transaction_fx_rate_origin", sa.String(length=24), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE transactions SET transaction_fx_rate_origin = 'LEGACY_UNKNOWN' "
            "WHERE transaction_fx_rate IS NOT NULL"
        )
    )
    op.create_check_constraint(
        "ck_transactions_fx_rate_origin",
        "transactions",
        "transaction_fx_rate_origin IS NULL OR transaction_fx_rate_origin IN "
        "('SOURCE_BOOKED', 'REFERENCE_DERIVED', 'LEGACY_UNKNOWN')",
        postgresql_not_valid=True,
    )
    op.execute(
        sa.text('ALTER TABLE "transactions" VALIDATE CONSTRAINT "ck_transactions_fx_rate_origin"')
    )


def downgrade() -> None:
    """Remove provenance while retaining the pre-existing numeric FX rate."""

    op.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
    op.drop_constraint("ck_transactions_fx_rate_origin", "transactions", type_="check")
    op.drop_column("transactions", "transaction_fx_rate_origin")
