"""Bound valuation claim and stale-recovery hot paths.

Revision ID: c160b2c3d527
Revises: c159b2c3d526
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c160b2c3d527"
down_revision: str | Sequence[str] | None = "c159b2c3d526"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_INDEX = "ix_portfolio_valuation_jobs_processing_lease_recovery"
_OLD_INDEX = "ix_portfolio_valuation_jobs_processing_lease_expiry"


def upgrade() -> None:
    """Replace the expiry-only index with deterministic recovery ordering."""

    with op.get_context().autocommit_block():
        op.create_index(
            _NEW_INDEX,
            "portfolio_valuation_jobs",
            ["valuation_lease_expires_at", "id"],
            postgresql_where=sa.text("status = 'PROCESSING'"),
            postgresql_concurrently=True,
        )
        op.drop_index(
            _OLD_INDEX,
            table_name="portfolio_valuation_jobs",
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    """Restore the prior expiry-only partial index."""

    with op.get_context().autocommit_block():
        op.create_index(
            _OLD_INDEX,
            "portfolio_valuation_jobs",
            ["valuation_lease_expires_at"],
            postgresql_where=sa.text("status = 'PROCESSING'"),
            postgresql_concurrently=True,
        )
        op.drop_index(
            _NEW_INDEX,
            table_name="portfolio_valuation_jobs",
            postgresql_concurrently=True,
        )
