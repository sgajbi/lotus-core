"""Add append-only lot amortized-cost source authority.

Revision ID: c140b2c3d50d
Revises: c139b2c3d50c
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c140b2c3d50d"
down_revision: str | Sequence[str] | None = "c139b2c3d50c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lot_amortized_cost_authority",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("authority_type", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("legal_book_id", sa.String(), nullable=False),
        sa.Column("portfolio_id", sa.String(), nullable=False),
        sa.Column("security_id", sa.String(), nullable=False),
        sa.Column("lot_id", sa.String(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("lifecycle_status", sa.String(), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("source_system", sa.String(), nullable=False),
        sa.Column("source_record_id", sa.String(), nullable=False),
        sa.Column("source_revision", sa.String(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("authority_content_hash", sa.String(length=64), nullable=False),
        sa.Column("authority_payload", postgresql.JSONB(none_as_null=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "authority_type IN ('POLICY_ASSIGNMENT', 'CLEAN_COST_BASIS', "
            "'AMORTIZATION_SCHEDULE', 'EFFECTIVE_YIELD')",
            name="ck_lot_amort_authority_type",
        ),
        sa.CheckConstraint(
            "tenant_id = btrim(tenant_id) AND tenant_id <> '' "
            "AND legal_book_id = btrim(legal_book_id) AND legal_book_id <> '' "
            "AND portfolio_id = btrim(portfolio_id) AND portfolio_id <> '' "
            "AND security_id = btrim(security_id) AND security_id <> '' "
            "AND lot_id = btrim(lot_id) AND lot_id <> ''",
            name="ck_lot_amort_authority_scope_normalized",
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name="ck_lot_amort_authority_effective_window",
        ),
        sa.CheckConstraint(
            "lifecycle_status IN ('ACTIVE', 'SUSPENDED', 'RETIRED')",
            name="ck_lot_amort_authority_status",
        ),
        sa.CheckConstraint(
            "source_version >= 1",
            name="ck_lot_amort_authority_version_positive",
        ),
        sa.CheckConstraint(
            "source_system = btrim(source_system) AND source_system <> '' "
            "AND source_record_id = btrim(source_record_id) AND source_record_id <> '' "
            "AND source_revision = btrim(source_revision) AND source_revision <> ''",
            name="ck_lot_amort_authority_source_normalized",
        ),
        sa.CheckConstraint(
            "authority_content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_lot_amort_authority_hash",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(authority_payload) = 'object'",
            name="ck_lot_amort_authority_payload_object",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "legal_book_id", "portfolio_id"],
            ["portfolios.tenant_id", "portfolios.legal_book_id", "portfolios.portfolio_id"],
            name="fk_lot_amort_authority_book_scope",
        ),
        sa.ForeignKeyConstraint(
            ["security_id"],
            ["instruments.security_id"],
            name="fk_lot_amort_authority_security",
        ),
        sa.ForeignKeyConstraint(
            ["lot_id", "portfolio_id", "security_id"],
            [
                "position_lot_state.lot_id",
                "position_lot_state.portfolio_id",
                "position_lot_state.security_id",
            ],
            name="fk_lot_amort_authority_lot_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_lot_amortized_cost_authority"),
        sa.UniqueConstraint(
            "authority_type",
            "tenant_id",
            "legal_book_id",
            "portfolio_id",
            "security_id",
            "lot_id",
            "source_system",
            "source_record_id",
            "source_version",
            name="uq_lot_amort_authority_source_version",
        ),
    )
    op.create_index(
        "ix_lot_amort_authority_scope_effective",
        "lot_amortized_cost_authority",
        [
            "tenant_id",
            "legal_book_id",
            "portfolio_id",
            "security_id",
            "lot_id",
            "authority_type",
            "valid_from",
            "valid_to",
        ],
    )
    op.create_index(
        "ix_lot_amort_authority_source_history",
        "lot_amortized_cost_authority",
        ["source_system", "source_record_id", sa.text("source_version DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_lot_amort_authority_source_history",
        table_name="lot_amortized_cost_authority",
    )
    op.drop_index(
        "ix_lot_amort_authority_scope_effective",
        table_name="lot_amortized_cost_authority",
    )
    op.drop_table("lot_amortized_cost_authority")
