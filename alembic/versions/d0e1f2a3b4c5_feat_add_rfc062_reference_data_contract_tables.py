"""feat: add rfc062 benchmark/index reference contract tables

Revision ID: d0e1f2a3b4c5
Revises: c3d4e5f6a7b8
Create Date: 2026-03-01 19:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "portfolio_benchmark_assignments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("portfolio_id", sa.String(), nullable=False),
        sa.Column("benchmark_id", sa.String(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("assignment_source", sa.String(), nullable=False),
        sa.Column("assignment_status", sa.String(), server_default="active", nullable=False),
        sa.Column("policy_pack_id", sa.String(), nullable=True),
        sa.Column("source_system", sa.String(), nullable=True),
        sa.Column(
            "assignment_recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("assignment_version", sa.Integer(), server_default="1", nullable=False),
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
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.portfolio_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "portfolio_id",
            "benchmark_id",
            "effective_from",
            "assignment_version",
            name="_portfolio_benchmark_assignment_uc",
        ),
    )
    op.create_index(
        "ix_portfolio_benchmark_assignments_portfolio_id",
        "portfolio_benchmark_assignments",
        ["portfolio_id"],
        unique=False,
    )
    op.create_index(
        "ix_portfolio_benchmark_assignments_benchmark_id",
        "portfolio_benchmark_assignments",
        ["benchmark_id"],
        unique=False,
    )
    op.create_index(
        "ix_portfolio_benchmark_assignments_effective_from",
        "portfolio_benchmark_assignments",
        ["effective_from"],
        unique=False,
    )
    op.create_index(
        "ix_portfolio_benchmark_assignments_effective_to",
        "portfolio_benchmark_assignments",
        ["effective_to"],
        unique=False,
    )
    op.create_index(
        "ix_portfolio_benchmark_assignments_assignment_status",
        "portfolio_benchmark_assignments",
        ["assignment_status"],
        unique=False,
    )

    op.create_table(
        "benchmark_definitions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("benchmark_id", sa.String(), nullable=False),
        sa.Column("benchmark_name", sa.String(), nullable=False),
        sa.Column("benchmark_type", sa.String(), nullable=False),
        sa.Column("benchmark_currency", sa.String(length=3), nullable=False),
        sa.Column("return_convention", sa.String(), nullable=False),
        sa.Column("benchmark_status", sa.String(), server_default="active", nullable=False),
        sa.Column("benchmark_family", sa.String(), nullable=True),
        sa.Column("benchmark_provider", sa.String(), nullable=True),
        sa.Column("rebalance_frequency", sa.String(), nullable=True),
        sa.Column("classification_set_id", sa.String(), nullable=True),
        sa.Column("classification_labels", sa.JSON(), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_vendor", sa.String(), nullable=True),
        sa.Column("source_record_id", sa.String(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "benchmark_id", "effective_from", name="_benchmark_definition_effective_uc"
        ),
    )
    op.create_index(
        "ix_benchmark_definitions_benchmark_id",
        "benchmark_definitions",
        ["benchmark_id"],
        unique=False,
    )
    op.create_index(
        "ix_benchmark_definitions_effective_from",
        "benchmark_definitions",
        ["effective_from"],
        unique=False,
    )
    op.create_index(
        "ix_benchmark_definitions_effective_to",
        "benchmark_definitions",
        ["effective_to"],
        unique=False,
    )
    op.create_index(
        "ix_benchmark_definitions_benchmark_status",
        "benchmark_definitions",
        ["benchmark_status"],
        unique=False,
    )
    op.create_index(
        "ix_benchmark_definitions_quality_status",
        "benchmark_definitions",
        ["quality_status"],
        unique=False,
    )

    op.create_table(
        "index_definitions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("index_id", sa.String(), nullable=False),
        sa.Column("index_name", sa.String(), nullable=False),
        sa.Column("index_currency", sa.String(length=3), nullable=False),
        sa.Column("index_type", sa.String(), nullable=True),
        sa.Column("index_status", sa.String(), server_default="active", nullable=False),
        sa.Column("index_provider", sa.String(), nullable=True),
        sa.Column("index_market", sa.String(), nullable=True),
        sa.Column("classification_set_id", sa.String(), nullable=True),
        sa.Column("classification_labels", sa.JSON(), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_vendor", sa.String(), nullable=True),
        sa.Column("source_record_id", sa.String(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("index_id", "effective_from", name="_index_definition_effective_uc"),
    )
    op.create_index(
        "ix_index_definitions_index_id", "index_definitions", ["index_id"], unique=False
    )
    op.create_index(
        "ix_index_definitions_effective_from", "index_definitions", ["effective_from"], unique=False
    )
    op.create_index(
        "ix_index_definitions_effective_to", "index_definitions", ["effective_to"], unique=False
    )
    op.create_index(
        "ix_index_definitions_index_status", "index_definitions", ["index_status"], unique=False
    )
    op.create_index(
        "ix_index_definitions_quality_status", "index_definitions", ["quality_status"], unique=False
    )

    op.create_table(
        "benchmark_composition_series",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("benchmark_id", sa.String(), nullable=False),
        sa.Column("index_id", sa.String(), nullable=False),
        sa.Column("composition_effective_from", sa.Date(), nullable=False),
        sa.Column("composition_effective_to", sa.Date(), nullable=True),
        sa.Column("composition_weight", sa.Numeric(precision=18, scale=10), nullable=False),
        sa.Column("rebalance_event_id", sa.String(), nullable=True),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_vendor", sa.String(), nullable=True),
        sa.Column("source_record_id", sa.String(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "benchmark_id",
            "index_id",
            "composition_effective_from",
            name="_benchmark_composition_effective_uc",
        ),
    )
    op.create_index(
        "ix_benchmark_composition_series_benchmark_id",
        "benchmark_composition_series",
        ["benchmark_id"],
        unique=False,
    )
    op.create_index(
        "ix_benchmark_composition_series_index_id",
        "benchmark_composition_series",
        ["index_id"],
        unique=False,
    )
    op.create_index(
        "ix_benchmark_composition_series_composition_effective_from",
        "benchmark_composition_series",
        ["composition_effective_from"],
        unique=False,
    )
    op.create_index(
        "ix_benchmark_composition_series_composition_effective_to",
        "benchmark_composition_series",
        ["composition_effective_to"],
        unique=False,
    )
    op.create_index(
        "ix_benchmark_composition_series_rebalance_event_id",
        "benchmark_composition_series",
        ["rebalance_event_id"],
        unique=False,
    )
    op.create_index(
        "ix_benchmark_composition_series_quality_status",
        "benchmark_composition_series",
        ["quality_status"],
        unique=False,
    )

    op.create_table(
        "index_price_series",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("series_id", sa.String(), nullable=False),
        sa.Column("index_id", sa.String(), nullable=False),
        sa.Column("series_date", sa.Date(), nullable=False),
        sa.Column("index_price", sa.Numeric(precision=18, scale=10), nullable=False),
        sa.Column("series_currency", sa.String(length=3), nullable=False),
        sa.Column("value_convention", sa.String(), nullable=False),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_vendor", sa.String(), nullable=True),
        sa.Column("source_record_id", sa.String(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("series_id", "index_id", "series_date", name="_index_price_series_uc"),
    )
    op.create_index(
        "ix_index_price_series_series_id", "index_price_series", ["series_id"], unique=False
    )
    op.create_index(
        "ix_index_price_series_index_id", "index_price_series", ["index_id"], unique=False
    )
    op.create_index(
        "ix_index_price_series_series_date", "index_price_series", ["series_date"], unique=False
    )
    op.create_index(
        "ix_index_price_series_quality_status",
        "index_price_series",
        ["quality_status"],
        unique=False,
    )

    op.create_table(
        "index_return_series",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("series_id", sa.String(), nullable=False),
        sa.Column("index_id", sa.String(), nullable=False),
        sa.Column("series_date", sa.Date(), nullable=False),
        sa.Column("index_return", sa.Numeric(precision=18, scale=10), nullable=False),
        sa.Column("return_period", sa.String(), nullable=False),
        sa.Column("return_convention", sa.String(), nullable=False),
        sa.Column("series_currency", sa.String(length=3), nullable=False),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_vendor", sa.String(), nullable=True),
        sa.Column("source_record_id", sa.String(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("series_id", "index_id", "series_date", name="_index_return_series_uc"),
    )
    op.create_index(
        "ix_index_return_series_series_id", "index_return_series", ["series_id"], unique=False
    )
    op.create_index(
        "ix_index_return_series_index_id", "index_return_series", ["index_id"], unique=False
    )
    op.create_index(
        "ix_index_return_series_series_date", "index_return_series", ["series_date"], unique=False
    )
    op.create_index(
        "ix_index_return_series_quality_status",
        "index_return_series",
        ["quality_status"],
        unique=False,
    )

    op.create_table(
        "benchmark_return_series",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("series_id", sa.String(), nullable=False),
        sa.Column("benchmark_id", sa.String(), nullable=False),
        sa.Column("series_date", sa.Date(), nullable=False),
        sa.Column("benchmark_return", sa.Numeric(precision=18, scale=10), nullable=False),
        sa.Column("return_period", sa.String(), nullable=False),
        sa.Column("return_convention", sa.String(), nullable=False),
        sa.Column("series_currency", sa.String(length=3), nullable=False),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_vendor", sa.String(), nullable=True),
        sa.Column("source_record_id", sa.String(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "series_id", "benchmark_id", "series_date", name="_benchmark_return_series_uc"
        ),
    )
    op.create_index(
        "ix_benchmark_return_series_series_id",
        "benchmark_return_series",
        ["series_id"],
        unique=False,
    )
    op.create_index(
        "ix_benchmark_return_series_benchmark_id",
        "benchmark_return_series",
        ["benchmark_id"],
        unique=False,
    )
    op.create_index(
        "ix_benchmark_return_series_series_date",
        "benchmark_return_series",
        ["series_date"],
        unique=False,
    )
    op.create_index(
        "ix_benchmark_return_series_quality_status",
        "benchmark_return_series",
        ["quality_status"],
        unique=False,
    )

    op.create_table(
        "risk_free_series",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("series_id", sa.String(), nullable=False),
        sa.Column("risk_free_curve_id", sa.String(), nullable=False),
        sa.Column("series_date", sa.Date(), nullable=False),
        sa.Column("value", sa.Numeric(precision=18, scale=10), nullable=False),
        sa.Column("value_convention", sa.String(), nullable=False),
        sa.Column("day_count_convention", sa.String(), nullable=True),
        sa.Column("compounding_convention", sa.String(), nullable=True),
        sa.Column("series_currency", sa.String(length=3), nullable=False),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_vendor", sa.String(), nullable=True),
        sa.Column("source_record_id", sa.String(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "series_id", "risk_free_curve_id", "series_date", name="_risk_free_series_uc"
        ),
    )
    op.create_index(
        "ix_risk_free_series_series_id", "risk_free_series", ["series_id"], unique=False
    )
    op.create_index(
        "ix_risk_free_series_risk_free_curve_id",
        "risk_free_series",
        ["risk_free_curve_id"],
        unique=False,
    )
    op.create_index(
        "ix_risk_free_series_series_date", "risk_free_series", ["series_date"], unique=False
    )
    op.create_index(
        "ix_risk_free_series_series_currency", "risk_free_series", ["series_currency"], unique=False
    )
    op.create_index(
        "ix_risk_free_series_quality_status", "risk_free_series", ["quality_status"], unique=False
    )

    op.create_table(
        "classification_taxonomy",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("classification_set_id", sa.String(), nullable=False),
        sa.Column("taxonomy_scope", sa.String(), nullable=False),
        sa.Column("dimension_name", sa.String(), nullable=False),
        sa.Column("dimension_value", sa.String(), nullable=False),
        sa.Column("dimension_description", sa.String(), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_vendor", sa.String(), nullable=True),
        sa.Column("source_record_id", sa.String(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "classification_set_id",
            "taxonomy_scope",
            "dimension_name",
            "dimension_value",
            "effective_from",
            name="_classification_taxonomy_effective_uc",
        ),
    )
    op.create_index(
        "ix_classification_taxonomy_classification_set_id",
        "classification_taxonomy",
        ["classification_set_id"],
        unique=False,
    )
    op.create_index(
        "ix_classification_taxonomy_taxonomy_scope",
        "classification_taxonomy",
        ["taxonomy_scope"],
        unique=False,
    )
    op.create_index(
        "ix_classification_taxonomy_dimension_name",
        "classification_taxonomy",
        ["dimension_name"],
        unique=False,
    )
    op.create_index(
        "ix_classification_taxonomy_dimension_value",
        "classification_taxonomy",
        ["dimension_value"],
        unique=False,
    )
    op.create_index(
        "ix_classification_taxonomy_effective_from",
        "classification_taxonomy",
        ["effective_from"],
        unique=False,
    )
    op.create_index(
        "ix_classification_taxonomy_effective_to",
        "classification_taxonomy",
        ["effective_to"],
        unique=False,
    )
    op.create_index(
        "ix_classification_taxonomy_quality_status",
        "classification_taxonomy",
        ["quality_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_classification_taxonomy_quality_status", table_name="classification_taxonomy")
    op.drop_index("ix_classification_taxonomy_effective_to", table_name="classification_taxonomy")
    op.drop_index("ix_classification_taxonomy_effective_from", table_name="classification_taxonomy")
    op.drop_index(
        "ix_classification_taxonomy_dimension_value", table_name="classification_taxonomy"
    )
    op.drop_index("ix_classification_taxonomy_dimension_name", table_name="classification_taxonomy")
    op.drop_index("ix_classification_taxonomy_taxonomy_scope", table_name="classification_taxonomy")
    op.drop_index(
        "ix_classification_taxonomy_classification_set_id", table_name="classification_taxonomy"
    )
    op.drop_table("classification_taxonomy")

    op.drop_index("ix_risk_free_series_quality_status", table_name="risk_free_series")
    op.drop_index("ix_risk_free_series_series_currency", table_name="risk_free_series")
    op.drop_index("ix_risk_free_series_series_date", table_name="risk_free_series")
    op.drop_index("ix_risk_free_series_risk_free_curve_id", table_name="risk_free_series")
    op.drop_index("ix_risk_free_series_series_id", table_name="risk_free_series")
    op.drop_table("risk_free_series")

    op.drop_index("ix_benchmark_return_series_quality_status", table_name="benchmark_return_series")
    op.drop_index("ix_benchmark_return_series_series_date", table_name="benchmark_return_series")
    op.drop_index("ix_benchmark_return_series_benchmark_id", table_name="benchmark_return_series")
    op.drop_index("ix_benchmark_return_series_series_id", table_name="benchmark_return_series")
    op.drop_table("benchmark_return_series")

    op.drop_index("ix_index_return_series_quality_status", table_name="index_return_series")
    op.drop_index("ix_index_return_series_series_date", table_name="index_return_series")
    op.drop_index("ix_index_return_series_index_id", table_name="index_return_series")
    op.drop_index("ix_index_return_series_series_id", table_name="index_return_series")
    op.drop_table("index_return_series")

    op.drop_index("ix_index_price_series_quality_status", table_name="index_price_series")
    op.drop_index("ix_index_price_series_series_date", table_name="index_price_series")
    op.drop_index("ix_index_price_series_index_id", table_name="index_price_series")
    op.drop_index("ix_index_price_series_series_id", table_name="index_price_series")
    op.drop_table("index_price_series")

    op.drop_index(
        "ix_benchmark_composition_series_quality_status", table_name="benchmark_composition_series"
    )
    op.drop_index(
        "ix_benchmark_composition_series_rebalance_event_id",
        table_name="benchmark_composition_series",
    )
    op.drop_index(
        "ix_benchmark_composition_series_composition_effective_to",
        table_name="benchmark_composition_series",
    )
    op.drop_index(
        "ix_benchmark_composition_series_composition_effective_from",
        table_name="benchmark_composition_series",
    )
    op.drop_index(
        "ix_benchmark_composition_series_index_id", table_name="benchmark_composition_series"
    )
    op.drop_index(
        "ix_benchmark_composition_series_benchmark_id", table_name="benchmark_composition_series"
    )
    op.drop_table("benchmark_composition_series")

    op.drop_index("ix_index_definitions_quality_status", table_name="index_definitions")
    op.drop_index("ix_index_definitions_index_status", table_name="index_definitions")
    op.drop_index("ix_index_definitions_effective_to", table_name="index_definitions")
    op.drop_index("ix_index_definitions_effective_from", table_name="index_definitions")
    op.drop_index("ix_index_definitions_index_id", table_name="index_definitions")
    op.drop_table("index_definitions")

    op.drop_index("ix_benchmark_definitions_quality_status", table_name="benchmark_definitions")
    op.drop_index("ix_benchmark_definitions_benchmark_status", table_name="benchmark_definitions")
    op.drop_index("ix_benchmark_definitions_effective_to", table_name="benchmark_definitions")
    op.drop_index("ix_benchmark_definitions_effective_from", table_name="benchmark_definitions")
    op.drop_index("ix_benchmark_definitions_benchmark_id", table_name="benchmark_definitions")
    op.drop_table("benchmark_definitions")

    op.drop_index(
        "ix_portfolio_benchmark_assignments_assignment_status",
        table_name="portfolio_benchmark_assignments",
    )
    op.drop_index(
        "ix_portfolio_benchmark_assignments_effective_to",
        table_name="portfolio_benchmark_assignments",
    )
    op.drop_index(
        "ix_portfolio_benchmark_assignments_effective_from",
        table_name="portfolio_benchmark_assignments",
    )
    op.drop_index(
        "ix_portfolio_benchmark_assignments_benchmark_id",
        table_name="portfolio_benchmark_assignments",
    )
    op.drop_index(
        "ix_portfolio_benchmark_assignments_portfolio_id",
        table_name="portfolio_benchmark_assignments",
    )
    op.drop_table("portfolio_benchmark_assignments")
