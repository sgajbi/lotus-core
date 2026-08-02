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

_PROFILE_SOURCES_ARRAY_JSONB = "jsonb_typeof(source_references) = 'array'"
_PROFILE_LIFECYCLE_JSONB = (
    "(status = 'ACTIVE' AND eligibility_reason IS NULL "
    "AND policy_id IS NOT NULL AND policy_version IS NOT NULL "
    "AND schedule_version IS NOT NULL AND currency IS NOT NULL "
    "AND direction IS NOT NULL AND initial_amortized_cost_local IS NOT NULL "
    "AND redemption_value_local IS NOT NULL "
    "AND final_amortized_cost_local IS NOT NULL AND residual_local IS NOT NULL "
    "AND authority_content_hash IS NOT NULL AND calculation_lineage IS NOT NULL "
    "AND jsonb_array_length(source_references) > 0) "
    "OR (status IN ('PARKED', 'INELIGIBLE') AND eligibility_reason IS NOT NULL "
    "AND direction IS NULL AND initial_amortized_cost_local IS NULL "
    "AND redemption_value_local IS NULL AND final_amortized_cost_local IS NULL "
    "AND residual_local IS NULL AND calculation_lineage IS NULL)"
)
_PROFILE_SOURCES_ARRAY_JSON = "json_typeof(source_references::json) = 'array'"
_PROFILE_LIFECYCLE_JSON = _PROFILE_LIFECYCLE_JSONB.replace(
    "jsonb_array_length(source_references)",
    "json_array_length(source_references::json)",
)


def upgrade() -> None:
    _upgrade_profile_json_evidence()
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
    _downgrade_profile_json_evidence()


def _upgrade_profile_json_evidence() -> None:
    op.drop_constraint(
        "ck_lot_amort_profile_lifecycle_shape",
        "lot_amortized_cost_profiles",
        type_="check",
    )
    op.drop_constraint(
        "ck_lot_amort_profile_sources_array",
        "lot_amortized_cost_profiles",
        type_="check",
    )
    op.alter_column(
        "lot_amortized_cost_profiles",
        "source_references",
        existing_type=sa.JSON(none_as_null=True),
        type_=postgresql.JSONB(none_as_null=True),
        existing_nullable=False,
        postgresql_using="source_references::jsonb",
    )
    op.alter_column(
        "lot_amortized_cost_profiles",
        "calculation_lineage",
        existing_type=sa.JSON(none_as_null=True),
        type_=postgresql.JSONB(none_as_null=True),
        existing_nullable=True,
        postgresql_using="calculation_lineage::jsonb",
    )
    op.create_check_constraint(
        "ck_lot_amort_profile_sources_array",
        "lot_amortized_cost_profiles",
        _PROFILE_SOURCES_ARRAY_JSONB,
    )
    op.create_check_constraint(
        "ck_lot_amort_profile_lifecycle_shape",
        "lot_amortized_cost_profiles",
        _PROFILE_LIFECYCLE_JSONB,
    )


def _downgrade_profile_json_evidence() -> None:
    op.drop_constraint(
        "ck_lot_amort_profile_lifecycle_shape",
        "lot_amortized_cost_profiles",
        type_="check",
    )
    op.drop_constraint(
        "ck_lot_amort_profile_sources_array",
        "lot_amortized_cost_profiles",
        type_="check",
    )
    op.alter_column(
        "lot_amortized_cost_profiles",
        "source_references",
        existing_type=postgresql.JSONB(none_as_null=True),
        type_=sa.JSON(none_as_null=True),
        existing_nullable=False,
        postgresql_using="source_references::json",
    )
    op.alter_column(
        "lot_amortized_cost_profiles",
        "calculation_lineage",
        existing_type=postgresql.JSONB(none_as_null=True),
        type_=sa.JSON(none_as_null=True),
        existing_nullable=True,
        postgresql_using="calculation_lineage::json",
    )
    op.create_check_constraint(
        "ck_lot_amort_profile_sources_array",
        "lot_amortized_cost_profiles",
        _PROFILE_SOURCES_ARRAY_JSON,
    )
    op.create_check_constraint(
        "ck_lot_amort_profile_lifecycle_shape",
        "lot_amortized_cost_profiles",
        _PROFILE_LIFECYCLE_JSON,
    )
