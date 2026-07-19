"""Add effective-dated instrument valuation-policy assignments.

Revision ID: c116b2c3d4f5
Revises: c115b2c3d4f4
Create Date: 2026-07-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c116b2c3d4f5"
down_revision: str | None = "c115b2c3d4f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create auditable valuation-policy assignment history and lookup indexes."""

    op.create_table(
        "instrument_valuation_policy_assignments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("legal_book_id", sa.String(), nullable=False),
        sa.Column("security_id", sa.String(), nullable=False),
        sa.Column("policy_id", sa.String(), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("assignment_status", sa.String(), nullable=False),
        sa.Column("assignment_version", sa.Integer(), nullable=False),
        sa.Column("source_system", sa.String(), nullable=False),
        sa.Column("source_record_id", sa.String(), nullable=False),
        sa.Column("source_revision", sa.String(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assignment_reason", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name="ck_inst_val_policy_effective_window",
        ),
        sa.CheckConstraint(
            "policy_version >= 1",
            name="ck_inst_val_policy_version_positive",
        ),
        sa.CheckConstraint(
            "assignment_version >= 1",
            name="ck_inst_val_assignment_version_positive",
        ),
        sa.CheckConstraint(
            "assignment_status IN ('ACTIVE', 'SUSPENDED', 'RETIRED')",
            name="ck_inst_val_assignment_status_governed",
        ),
        sa.ForeignKeyConstraint(["security_id"], ["instruments.security_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "legal_book_id",
            "security_id",
            "source_system",
            "source_record_id",
            "assignment_version",
            name="uq_inst_val_policy_source_version",
        ),
    )
    op.create_index(
        "ix_inst_val_policy_scope_effective",
        "instrument_valuation_policy_assignments",
        ["tenant_id", "legal_book_id", "security_id", "valid_from", "valid_to"],
        postgresql_where=sa.text("assignment_status = 'ACTIVE'"),
    )
    op.create_index(
        "ix_inst_val_policy_source_history",
        "instrument_valuation_policy_assignments",
        [
            "tenant_id",
            "legal_book_id",
            "security_id",
            "source_system",
            "source_record_id",
            sa.text("assignment_version DESC"),
        ],
    )


def downgrade() -> None:
    """Remove instrument valuation-policy assignment history."""

    op.drop_index(
        "ix_inst_val_policy_source_history",
        table_name="instrument_valuation_policy_assignments",
    )
    op.drop_index(
        "ix_inst_val_policy_scope_effective",
        table_name="instrument_valuation_policy_assignments",
    )
    op.drop_table("instrument_valuation_policy_assignments")
