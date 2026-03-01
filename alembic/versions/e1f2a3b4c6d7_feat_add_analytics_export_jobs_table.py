"""feat: add analytics export jobs table

Revision ID: e1f2a3b4c6d7
Revises: d0e1f2a3b4c5
Create Date: 2026-03-01 21:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c6d7"
down_revision: Union[str, None] = "d0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analytics_export_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(), nullable=False),
        sa.Column("dataset_type", sa.String(), nullable=False),
        sa.Column("portfolio_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), server_default="accepted", nullable=False),
        sa.Column("request_fingerprint", sa.String(), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("result_payload", sa.JSON(), nullable=True),
        sa.Column("result_row_count", sa.Integer(), nullable=True),
        sa.Column("result_format", sa.String(), server_default="json", nullable=False),
        sa.Column("compression", sa.String(), server_default="none", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_analytics_export_jobs_dataset_type"), "analytics_export_jobs", ["dataset_type"], unique=False)
    op.create_index(op.f("ix_analytics_export_jobs_job_id"), "analytics_export_jobs", ["job_id"], unique=True)
    op.create_index(op.f("ix_analytics_export_jobs_portfolio_id"), "analytics_export_jobs", ["portfolio_id"], unique=False)
    op.create_index(
        op.f("ix_analytics_export_jobs_request_fingerprint"),
        "analytics_export_jobs",
        ["request_fingerprint"],
        unique=False,
    )
    op.create_index(op.f("ix_analytics_export_jobs_status"), "analytics_export_jobs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_analytics_export_jobs_status"), table_name="analytics_export_jobs")
    op.drop_index(op.f("ix_analytics_export_jobs_request_fingerprint"), table_name="analytics_export_jobs")
    op.drop_index(op.f("ix_analytics_export_jobs_portfolio_id"), table_name="analytics_export_jobs")
    op.drop_index(op.f("ix_analytics_export_jobs_job_id"), table_name="analytics_export_jobs")
    op.drop_index(op.f("ix_analytics_export_jobs_dataset_type"), table_name="analytics_export_jobs")
    op.drop_table("analytics_export_jobs")
