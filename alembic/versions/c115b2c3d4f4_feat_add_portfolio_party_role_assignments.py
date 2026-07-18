"""Add effective-dated portfolio party-role assignments.

Revision ID: c115b2c3d4f4
Revises: c114b2c3d4f3
Create Date: 2026-07-18
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c115b2c3d4f4"
down_revision: str | None = "c114b2c3d4f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLE_TYPES = (
    "relationship_manager",
    "investment_advisor",
    "portfolio_manager",
    "discretionary_portfolio_manager",
    "assistant_rm",
    "service_officer",
    "external_asset_manager",
    "temporary_coverage_delegate",
)
ROLE_SCOPES = (
    "relationship_coverage",
    "investment_advice",
    "portfolio_management",
    "client_service",
)
QUALITY_STATUSES = ("accepted", "pending_review", "quarantined", "rejected")


def _sql_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    """Create the source-owned role-assignment aggregate and lookup indexes."""

    op.create_table(
        "portfolio_party_role_assignments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("portfolio_id", sa.String(), nullable=False),
        sa.Column("party_id", sa.String(), nullable=False),
        sa.Column("role_type", sa.String(), nullable=False),
        sa.Column("role_scope", sa.String(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("assignment_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("source_system", sa.String(), nullable=False),
        sa.Column("source_record_id", sa.String(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quality_status", sa.String(), server_default="accepted", nullable=False),
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
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_party_role_effective_window",
        ),
        sa.CheckConstraint(
            "assignment_version >= 1",
            name="ck_party_role_assignment_version_positive",
        ),
        sa.CheckConstraint(
            f"role_type IN ({_sql_values(ROLE_TYPES)})",
            name="ck_party_role_type_governed",
        ),
        sa.CheckConstraint(
            f"role_scope IN ({_sql_values(ROLE_SCOPES)})",
            name="ck_party_role_scope_governed",
        ),
        sa.CheckConstraint(
            f"quality_status IN ({_sql_values(QUALITY_STATUSES)})",
            name="ck_party_role_quality_governed",
        ),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.portfolio_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_system",
            "source_record_id",
            "assignment_version",
            name="uq_party_role_source_record_version",
        ),
    )
    op.create_index(
        "ix_party_role_portfolio_effective",
        "portfolio_party_role_assignments",
        ["portfolio_id", "effective_from", "effective_to", "role_type"],
        postgresql_where=sa.text("quality_status = 'accepted'"),
    )
    op.create_index(
        "ix_party_role_party_effective",
        "portfolio_party_role_assignments",
        [
            "party_id",
            "role_type",
            "role_scope",
            "effective_from",
            "effective_to",
            "portfolio_id",
        ],
        postgresql_where=sa.text("quality_status = 'accepted'"),
    )


def downgrade() -> None:
    """Remove the portfolio party-role assignment aggregate."""

    op.drop_index(
        "ix_party_role_party_effective", table_name="portfolio_party_role_assignments"
    )
    op.drop_index(
        "ix_party_role_portfolio_effective", table_name="portfolio_party_role_assignments"
    )
    op.drop_table("portfolio_party_role_assignments")
