"""feat: add financial reconciliation control tables

Revision ID: f9b0c1d2e3f4
Revises: e0f1a2b3c4d5
Create Date: 2026-03-08 16:10:00
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f9b0c1d2e3f4"
down_revision: Union[str, None] = "e0f1a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "financial_reconciliation_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("reconciliation_type", sa.String(), nullable=False),
        sa.Column("portfolio_id", sa.String(), nullable=True),
        sa.Column("business_date", sa.Date(), nullable=True),
        sa.Column("epoch", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="RUNNING"),
        sa.Column("requested_by", sa.String(), nullable=True),
        sa.Column("correlation_id", sa.String(), nullable=True),
        sa.Column("tolerance", sa.Numeric(18, 10), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id"),
    )
    op.create_index(
        "ix_financial_reconciliation_runs_run_id",
        "financial_reconciliation_runs",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_financial_reconciliation_runs_reconciliation_type",
        "financial_reconciliation_runs",
        ["reconciliation_type"],
        unique=False,
    )
    op.create_index(
        "ix_financial_reconciliation_runs_portfolio_id",
        "financial_reconciliation_runs",
        ["portfolio_id"],
        unique=False,
    )
    op.create_index(
        "ix_financial_reconciliation_runs_business_date",
        "financial_reconciliation_runs",
        ["business_date"],
        unique=False,
    )
    op.create_index(
        "ix_financial_reconciliation_runs_epoch",
        "financial_reconciliation_runs",
        ["epoch"],
        unique=False,
    )
    op.create_index(
        "ix_financial_reconciliation_runs_status",
        "financial_reconciliation_runs",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_financial_reconciliation_runs_type_status_started_at",
        "financial_reconciliation_runs",
        ["reconciliation_type", "status", sa.text("started_at DESC")],
        unique=False,
    )

    op.create_table(
        "financial_reconciliation_findings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("finding_id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("reconciliation_type", sa.String(), nullable=False),
        sa.Column("finding_type", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("portfolio_id", sa.String(), nullable=True),
        sa.Column("security_id", sa.String(), nullable=True),
        sa.Column("transaction_id", sa.String(), nullable=True),
        sa.Column("business_date", sa.Date(), nullable=True),
        sa.Column("epoch", sa.Integer(), nullable=True),
        sa.Column("expected_value", sa.JSON(), nullable=True),
        sa.Column("observed_value", sa.JSON(), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["run_id"], ["financial_reconciliation_runs.run_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("finding_id"),
    )
    op.create_index(
        "ix_financial_reconciliation_findings_finding_id",
        "financial_reconciliation_findings",
        ["finding_id"],
        unique=False,
    )
    op.create_index(
        "ix_financial_reconciliation_findings_run_id",
        "financial_reconciliation_findings",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_financial_reconciliation_findings_reconciliation_type",
        "financial_reconciliation_findings",
        ["reconciliation_type"],
        unique=False,
    )
    op.create_index(
        "ix_financial_reconciliation_findings_finding_type",
        "financial_reconciliation_findings",
        ["finding_type"],
        unique=False,
    )
    op.create_index(
        "ix_financial_reconciliation_findings_severity",
        "financial_reconciliation_findings",
        ["severity"],
        unique=False,
    )
    op.create_index(
        "ix_financial_reconciliation_findings_portfolio_id",
        "financial_reconciliation_findings",
        ["portfolio_id"],
        unique=False,
    )
    op.create_index(
        "ix_financial_reconciliation_findings_security_id",
        "financial_reconciliation_findings",
        ["security_id"],
        unique=False,
    )
    op.create_index(
        "ix_financial_reconciliation_findings_transaction_id",
        "financial_reconciliation_findings",
        ["transaction_id"],
        unique=False,
    )
    op.create_index(
        "ix_financial_reconciliation_findings_business_date",
        "financial_reconciliation_findings",
        ["business_date"],
        unique=False,
    )
    op.create_index(
        "ix_financial_reconciliation_findings_epoch",
        "financial_reconciliation_findings",
        ["epoch"],
        unique=False,
    )
    op.create_index(
        "ix_financial_reconciliation_findings_run_type_severity",
        "financial_reconciliation_findings",
        ["run_id", "finding_type", "severity"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_financial_reconciliation_findings_run_type_severity",
        table_name="financial_reconciliation_findings",
    )
    op.drop_index("ix_financial_reconciliation_findings_epoch", table_name="financial_reconciliation_findings")
    op.drop_index(
        "ix_financial_reconciliation_findings_business_date",
        table_name="financial_reconciliation_findings",
    )
    op.drop_index(
        "ix_financial_reconciliation_findings_transaction_id",
        table_name="financial_reconciliation_findings",
    )
    op.drop_index(
        "ix_financial_reconciliation_findings_security_id",
        table_name="financial_reconciliation_findings",
    )
    op.drop_index(
        "ix_financial_reconciliation_findings_portfolio_id",
        table_name="financial_reconciliation_findings",
    )
    op.drop_index("ix_financial_reconciliation_findings_severity", table_name="financial_reconciliation_findings")
    op.drop_index(
        "ix_financial_reconciliation_findings_finding_type",
        table_name="financial_reconciliation_findings",
    )
    op.drop_index(
        "ix_financial_reconciliation_findings_reconciliation_type",
        table_name="financial_reconciliation_findings",
    )
    op.drop_index("ix_financial_reconciliation_findings_run_id", table_name="financial_reconciliation_findings")
    op.drop_index(
        "ix_financial_reconciliation_findings_finding_id",
        table_name="financial_reconciliation_findings",
    )
    op.drop_table("financial_reconciliation_findings")

    op.drop_index(
        "ix_financial_reconciliation_runs_type_status_started_at",
        table_name="financial_reconciliation_runs",
    )
    op.drop_index("ix_financial_reconciliation_runs_status", table_name="financial_reconciliation_runs")
    op.drop_index("ix_financial_reconciliation_runs_epoch", table_name="financial_reconciliation_runs")
    op.drop_index(
        "ix_financial_reconciliation_runs_business_date",
        table_name="financial_reconciliation_runs",
    )
    op.drop_index("ix_financial_reconciliation_runs_portfolio_id", table_name="financial_reconciliation_runs")
    op.drop_index(
        "ix_financial_reconciliation_runs_reconciliation_type",
        table_name="financial_reconciliation_runs",
    )
    op.drop_index("ix_financial_reconciliation_runs_run_id", table_name="financial_reconciliation_runs")
    op.drop_table("financial_reconciliation_runs")
