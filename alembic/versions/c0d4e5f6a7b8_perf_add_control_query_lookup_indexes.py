"""perf add control query lookup indexes

Revision ID: c0d4e5f6a7b8
Revises: c0d3e4f5a6b7
Create Date: 2026-05-28 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c0d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "c0d3e4f5a6b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_analytics_export_jobs_dataset_fingerprint_id",
        "analytics_export_jobs",
        ["dataset_type", "request_fingerprint", sa.text("id DESC")],
        unique=False,
    )
    op.create_index(
        "ix_financial_reconciliation_findings_run_severity_created_id",
        "financial_reconciliation_findings",
        ["run_id", "severity", sa.text("created_at DESC"), sa.text("id DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_financial_reconciliation_findings_run_severity_created_id",
        table_name="financial_reconciliation_findings",
    )
    op.drop_index(
        "ix_analytics_export_jobs_dataset_fingerprint_id",
        table_name="analytics_export_jobs",
    )
