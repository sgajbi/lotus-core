"""Add fenced leases to durable reprocessing jobs.

Revision ID: c161b2c3d528
Revises: c160b2c3d527
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c161b2c3d528"
down_revision: str | Sequence[str] | None = "c160b2c3d527"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE_NAME = "reprocessing_jobs"
_LEASE_CUTOVER_GUARD = sa.text(
    """
    DO $$
    BEGIN
        IF EXISTS (
            SELECT 1
            FROM reprocessing_jobs
            WHERE status = 'PROCESSING'
        ) THEN
            RAISE EXCEPTION USING
                MESSAGE = 'reprocessing lease cutover requires a drained PROCESSING queue',
                HINT = 'pause the old worker, recover or terminalize in-flight rows, then retry';
        END IF;
    END
    $$
    """
)
_PROCESSING_LEASE_CHECK = (
    "(status = 'PROCESSING' AND lease_owner IS NOT NULL "
    "AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL) OR "
    "(status <> 'PROCESSING' AND lease_owner IS NULL "
    "AND lease_token IS NULL AND lease_expires_at IS NULL)"
)


def upgrade() -> None:
    """Require a quiesced cutover, then add recoverable lease authority."""

    op.execute(_LEASE_CUTOVER_GUARD)
    op.add_column(_TABLE_NAME, sa.Column("lease_owner", sa.String(128), nullable=True))
    op.add_column(_TABLE_NAME, sa.Column("lease_token", sa.String(64), nullable=True))
    op.add_column(
        _TABLE_NAME,
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_reprocessing_jobs_processing_lease",
        _TABLE_NAME,
        _PROCESSING_LEASE_CHECK,
    )
    op.create_check_constraint(
        "ck_reprocessing_jobs_lease_owner_normalized",
        _TABLE_NAME,
        "lease_owner IS NULL OR (lease_owner = btrim(lease_owner) AND lease_owner <> '')",
    )
    op.create_check_constraint(
        "ck_reprocessing_jobs_lease_token",
        _TABLE_NAME,
        "lease_token IS NULL OR lease_token ~ '^[0-9a-f]{32}$'",
    )
    op.create_index(
        "ix_reprocessing_jobs_processing_lease_recovery",
        _TABLE_NAME,
        ["lease_expires_at", "id"],
        postgresql_where=sa.text("status = 'PROCESSING'"),
    )


def downgrade() -> None:
    """Remove lease authority only after the leased queue has drained."""

    op.execute(_LEASE_CUTOVER_GUARD)
    op.drop_index(
        "ix_reprocessing_jobs_processing_lease_recovery",
        table_name=_TABLE_NAME,
    )
    op.drop_constraint(
        "ck_reprocessing_jobs_lease_token",
        _TABLE_NAME,
        type_="check",
    )
    op.drop_constraint(
        "ck_reprocessing_jobs_lease_owner_normalized",
        _TABLE_NAME,
        type_="check",
    )
    op.drop_constraint(
        "ck_reprocessing_jobs_processing_lease",
        _TABLE_NAME,
        type_="check",
    )
    op.drop_column(_TABLE_NAME, "lease_expires_at")
    op.drop_column(_TABLE_NAME, "lease_token")
    op.drop_column(_TABLE_NAME, "lease_owner")
