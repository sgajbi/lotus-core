"""Add valuation claim-generation ownership token.

Revision ID: c151b2c3d518
Revises: c150b2c3d517
Create Date: 2026-08-10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c151b2c3d518"
down_revision: str | Sequence[str] | None = "c150b2c3d517"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persist the opaque token that owns one active valuation claim."""

    op.add_column(
        "portfolio_valuation_jobs",
        sa.Column("valuation_claim_token", sa.String(length=32), nullable=True),
    )
    op.create_check_constraint(
        "ck_portfolio_valuation_jobs_claim_token",
        "portfolio_valuation_jobs",
        "valuation_claim_token IS NULL OR "
        "valuation_claim_token ~ '^[0-9a-f]{32}$'",
    )


def downgrade() -> None:
    """Remove valuation claim-generation ownership."""

    op.drop_constraint(
        "ck_portfolio_valuation_jobs_claim_token",
        "portfolio_valuation_jobs",
        type_="check",
    )
    op.drop_column("portfolio_valuation_jobs", "valuation_claim_token")
