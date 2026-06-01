"""perf: reorder reconciliation finding list index

Revision ID: c0e2f3a4b5c6
Revises: c0e1f2a3b4c5
Create Date: 2026-05-29 10:55:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c0e2f3a4b5c6"
down_revision: str | Sequence[str] | None = "c0e1f2a3b4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index(
        "ix_financial_reconciliation_findings_run_type_severity",
        table_name="financial_reconciliation_findings",
    )
    op.create_index(
        "ix_financial_reconciliation_findings_run_severity_type_id",
        "financial_reconciliation_findings",
        ["run_id", "severity", "finding_type", sa.text("id ASC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_financial_reconciliation_findings_run_severity_type_id",
        table_name="financial_reconciliation_findings",
    )
    op.create_index(
        "ix_financial_reconciliation_findings_run_type_severity",
        "financial_reconciliation_findings",
        ["run_id", "finding_type", "severity"],
        unique=False,
    )
