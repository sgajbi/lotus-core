"""Add explicit owner and expiry to valuation job claims.

Revision ID: c156b2c3d523
Revises: c155b2c3d522
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c156b2c3d523"
down_revision: str | Sequence[str] | None = "c155b2c3d522"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persist bounded valuation ownership and database-clock expiry."""

    op.add_column(
        "portfolio_valuation_jobs",
        sa.Column("valuation_lease_owner", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "portfolio_valuation_jobs",
        sa.Column("valuation_lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Claims created by the token-only predecessor have no authoritative expiry. Requeue them
    # instead of fabricating lease authority or allowing an unbounded PROCESSING row to survive.
    op.execute(
        sa.text(
            """
            UPDATE portfolio_valuation_jobs
            SET status = 'PENDING',
                valuation_claim_token = NULL,
                requeue_requested = false,
                updated_at = clock_timestamp()
            WHERE status = 'PROCESSING'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE portfolio_valuation_jobs
            SET valuation_claim_token = NULL
            WHERE status <> 'PROCESSING' AND valuation_claim_token IS NOT NULL
            """
        )
    )
    op.create_check_constraint(
        "ck_portfolio_valuation_jobs_lease_all_or_none",
        "portfolio_valuation_jobs",
        "(valuation_lease_owner IS NULL AND valuation_claim_token IS NULL "
        "AND valuation_lease_expires_at IS NULL) OR "
        "(valuation_lease_owner IS NOT NULL AND valuation_claim_token IS NOT NULL "
        "AND valuation_lease_expires_at IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_portfolio_valuation_jobs_lease_owner_nonblank",
        "portfolio_valuation_jobs",
        "valuation_lease_owner IS NULL OR btrim(valuation_lease_owner) <> ''",
    )
    op.create_check_constraint(
        "ck_portfolio_valuation_jobs_lease_expiry_finite",
        "portfolio_valuation_jobs",
        "valuation_lease_expires_at IS NULL OR valuation_lease_expires_at "
        "NOT IN ('infinity'::timestamptz, '-infinity'::timestamptz)",
    )
    op.create_check_constraint(
        "ck_portfolio_valuation_jobs_processing_lease_state",
        "portfolio_valuation_jobs",
        "(status = 'PROCESSING' AND valuation_lease_owner IS NOT NULL "
        "AND valuation_claim_token IS NOT NULL AND valuation_lease_expires_at IS NOT NULL) "
        "OR (status <> 'PROCESSING' AND valuation_lease_owner IS NULL "
        "AND valuation_claim_token IS NULL AND valuation_lease_expires_at IS NULL)",
    )
    op.create_index(
        "ix_portfolio_valuation_jobs_processing_lease_expiry",
        "portfolio_valuation_jobs",
        ["valuation_lease_expires_at"],
        postgresql_where=sa.text("status = 'PROCESSING'"),
    )


def downgrade() -> None:
    """Remove valuation lease owner and expiry while retaining claim tokens."""

    op.drop_index(
        "ix_portfolio_valuation_jobs_processing_lease_expiry",
        table_name="portfolio_valuation_jobs",
    )
    op.drop_constraint(
        "ck_portfolio_valuation_jobs_processing_lease_state",
        "portfolio_valuation_jobs",
        type_="check",
    )
    op.drop_constraint(
        "ck_portfolio_valuation_jobs_lease_expiry_finite",
        "portfolio_valuation_jobs",
        type_="check",
    )
    op.drop_constraint(
        "ck_portfolio_valuation_jobs_lease_owner_nonblank",
        "portfolio_valuation_jobs",
        type_="check",
    )
    op.drop_constraint(
        "ck_portfolio_valuation_jobs_lease_all_or_none",
        "portfolio_valuation_jobs",
        type_="check",
    )
    op.drop_column("portfolio_valuation_jobs", "valuation_lease_expires_at")
    op.drop_column("portfolio_valuation_jobs", "valuation_lease_owner")
