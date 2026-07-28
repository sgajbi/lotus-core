"""Add durable ingestion failure outcomes for deterministic idempotent replay.

Revision ID: c121b2c3d4fa
Revises: c120b2c3d4f9
Create Date: 2026-07-28 11:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c121b2c3d4fa"
down_revision: str | Sequence[str] | None = "c120b2c3d4f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT_NAME = "ck_ingestion_jobs_failure_outcome_complete"


def upgrade() -> None:
    """Add nullable response evidence without rewriting retained ingestion jobs."""

    op.add_column("ingestion_jobs", sa.Column("failure_status_code", sa.Integer(), nullable=True))
    op.add_column("ingestion_jobs", sa.Column("failure_code", sa.String(), nullable=True))
    op.add_column("ingestion_jobs", sa.Column("failure_detail", sa.JSON(), nullable=True))
    op.add_column("ingestion_jobs", sa.Column("failure_headers", sa.JSON(), nullable=True))
    op.create_check_constraint(
        _CONSTRAINT_NAME,
        "ingestion_jobs",
        "(failure_status_code IS NULL AND failure_code IS NULL "
        "AND failure_detail IS NULL AND failure_headers IS NULL) OR "
        "(failure_status_code IS NOT NULL "
        "AND failure_status_code BETWEEN 400 AND 599 "
        "AND failure_code IS NOT NULL "
        "AND failure_code = btrim(failure_code) "
        "AND failure_code <> '')",
        postgresql_not_valid=True,
    )
    op.execute(f'ALTER TABLE "ingestion_jobs" VALIDATE CONSTRAINT "{_CONSTRAINT_NAME}"')


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT_NAME, "ingestion_jobs", type_="check")
    op.drop_column("ingestion_jobs", "failure_headers")
    op.drop_column("ingestion_jobs", "failure_detail")
    op.drop_column("ingestion_jobs", "failure_code")
    op.drop_column("ingestion_jobs", "failure_status_code")
