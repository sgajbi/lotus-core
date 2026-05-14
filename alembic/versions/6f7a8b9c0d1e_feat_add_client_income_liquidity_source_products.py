"""add client income and liquidity source products

Revision ID: 6f7a8b9c0d1e
Revises: 5e6f7a8b9c0d
Create Date: 2026-05-14 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "6f7a8b9c0d1e"
down_revision: str | None = "5e6f7a8b9c0d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "client_income_needs_schedules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("client_id", sa.String(), nullable=False),
        sa.Column("portfolio_id", sa.String(), nullable=False),
        sa.Column("mandate_id", sa.String(), nullable=True),
        sa.Column("schedule_id", sa.String(), nullable=False),
        sa.Column("need_type", sa.String(), nullable=False),
        sa.Column("need_status", sa.String(), server_default="active", nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("frequency", sa.String(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("priority", sa.Integer(), server_default="1", nullable=False),
        sa.Column("funding_policy", sa.String(), nullable=True),
        sa.Column("source_system", sa.String(), nullable=True),
        sa.Column("source_record_id", sa.String(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quality_status", sa.String(), server_default="accepted", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.portfolio_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "client_id",
            "portfolio_id",
            "schedule_id",
            "start_date",
            name="_client_income_needs_schedule_effective_uc",
        ),
    )
    op.create_index(
        "ix_client_income_needs_schedules_client_id", "client_income_needs_schedules", ["client_id"]
    )
    op.create_index(
        "ix_client_income_needs_schedules_portfolio_id",
        "client_income_needs_schedules",
        ["portfolio_id"],
    )
    op.create_index(
        "ix_client_income_needs_schedules_mandate_id",
        "client_income_needs_schedules",
        ["mandate_id"],
    )
    op.create_index(
        "ix_client_income_needs_schedules_schedule_id",
        "client_income_needs_schedules",
        ["schedule_id"],
    )
    op.create_index(
        "ix_client_income_needs_schedules_need_type", "client_income_needs_schedules", ["need_type"]
    )
    op.create_index(
        "ix_client_income_needs_schedules_need_status",
        "client_income_needs_schedules",
        ["need_status"],
    )
    op.create_index(
        "ix_client_income_needs_schedules_currency", "client_income_needs_schedules", ["currency"]
    )
    op.create_index(
        "ix_client_income_needs_schedules_frequency", "client_income_needs_schedules", ["frequency"]
    )
    op.create_index(
        "ix_client_income_needs_schedules_start_date",
        "client_income_needs_schedules",
        ["start_date"],
    )
    op.create_index(
        "ix_client_income_needs_schedules_end_date", "client_income_needs_schedules", ["end_date"]
    )
    op.create_index(
        "ix_client_income_needs_schedules_quality_status",
        "client_income_needs_schedules",
        ["quality_status"],
    )
    op.create_index(
        "ix_client_income_needs_schedule_effective_window",
        "client_income_needs_schedules",
        ["portfolio_id", "client_id", "start_date", "end_date"],
    )

    op.create_table(
        "liquidity_reserve_requirements",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("client_id", sa.String(), nullable=False),
        sa.Column("portfolio_id", sa.String(), nullable=False),
        sa.Column("mandate_id", sa.String(), nullable=True),
        sa.Column("reserve_requirement_id", sa.String(), nullable=False),
        sa.Column("reserve_type", sa.String(), nullable=False),
        sa.Column("reserve_status", sa.String(), server_default="active", nullable=False),
        sa.Column("required_amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("priority", sa.Integer(), server_default="1", nullable=False),
        sa.Column("policy_source", sa.String(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("requirement_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("source_system", sa.String(), nullable=True),
        sa.Column("source_record_id", sa.String(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quality_status", sa.String(), server_default="accepted", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.portfolio_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "client_id",
            "portfolio_id",
            "reserve_requirement_id",
            "effective_from",
            "requirement_version",
            name="_liquidity_reserve_requirement_effective_uc",
        ),
    )
    op.create_index(
        "ix_liquidity_reserve_requirements_client_id",
        "liquidity_reserve_requirements",
        ["client_id"],
    )
    op.create_index(
        "ix_liquidity_reserve_requirements_portfolio_id",
        "liquidity_reserve_requirements",
        ["portfolio_id"],
    )
    op.create_index(
        "ix_liquidity_reserve_requirements_mandate_id",
        "liquidity_reserve_requirements",
        ["mandate_id"],
    )
    op.create_index(
        "ix_liquidity_reserve_requirements_reserve_requirement_id",
        "liquidity_reserve_requirements",
        ["reserve_requirement_id"],
    )
    op.create_index(
        "ix_liquidity_reserve_requirements_reserve_type",
        "liquidity_reserve_requirements",
        ["reserve_type"],
    )
    op.create_index(
        "ix_liquidity_reserve_requirements_reserve_status",
        "liquidity_reserve_requirements",
        ["reserve_status"],
    )
    op.create_index(
        "ix_liquidity_reserve_requirements_currency", "liquidity_reserve_requirements", ["currency"]
    )
    op.create_index(
        "ix_liquidity_reserve_requirements_effective_from",
        "liquidity_reserve_requirements",
        ["effective_from"],
    )
    op.create_index(
        "ix_liquidity_reserve_requirements_effective_to",
        "liquidity_reserve_requirements",
        ["effective_to"],
    )
    op.create_index(
        "ix_liquidity_reserve_requirements_quality_status",
        "liquidity_reserve_requirements",
        ["quality_status"],
    )
    op.create_index(
        "ix_liquidity_reserve_requirement_effective_window",
        "liquidity_reserve_requirements",
        ["portfolio_id", "client_id", "effective_from", "effective_to"],
    )

    op.create_table(
        "planned_withdrawal_schedules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("client_id", sa.String(), nullable=False),
        sa.Column("portfolio_id", sa.String(), nullable=False),
        sa.Column("mandate_id", sa.String(), nullable=True),
        sa.Column("withdrawal_schedule_id", sa.String(), nullable=False),
        sa.Column("withdrawal_type", sa.String(), nullable=False),
        sa.Column("withdrawal_status", sa.String(), server_default="active", nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("scheduled_date", sa.Date(), nullable=False),
        sa.Column("recurrence_frequency", sa.String(), nullable=True),
        sa.Column("purpose_code", sa.String(), nullable=True),
        sa.Column("source_system", sa.String(), nullable=True),
        sa.Column("source_record_id", sa.String(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quality_status", sa.String(), server_default="accepted", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.portfolio_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "client_id",
            "portfolio_id",
            "withdrawal_schedule_id",
            "scheduled_date",
            name="_planned_withdrawal_schedule_effective_uc",
        ),
    )
    op.create_index(
        "ix_planned_withdrawal_schedules_client_id", "planned_withdrawal_schedules", ["client_id"]
    )
    op.create_index(
        "ix_planned_withdrawal_schedules_portfolio_id",
        "planned_withdrawal_schedules",
        ["portfolio_id"],
    )
    op.create_index(
        "ix_planned_withdrawal_schedules_mandate_id", "planned_withdrawal_schedules", ["mandate_id"]
    )
    op.create_index(
        "ix_planned_withdrawal_schedules_withdrawal_schedule_id",
        "planned_withdrawal_schedules",
        ["withdrawal_schedule_id"],
    )
    op.create_index(
        "ix_planned_withdrawal_schedules_withdrawal_type",
        "planned_withdrawal_schedules",
        ["withdrawal_type"],
    )
    op.create_index(
        "ix_planned_withdrawal_schedules_withdrawal_status",
        "planned_withdrawal_schedules",
        ["withdrawal_status"],
    )
    op.create_index(
        "ix_planned_withdrawal_schedules_currency", "planned_withdrawal_schedules", ["currency"]
    )
    op.create_index(
        "ix_planned_withdrawal_schedules_scheduled_date",
        "planned_withdrawal_schedules",
        ["scheduled_date"],
    )
    op.create_index(
        "ix_planned_withdrawal_schedules_recurrence_frequency",
        "planned_withdrawal_schedules",
        ["recurrence_frequency"],
    )
    op.create_index(
        "ix_planned_withdrawal_schedules_purpose_code",
        "planned_withdrawal_schedules",
        ["purpose_code"],
    )
    op.create_index(
        "ix_planned_withdrawal_schedules_quality_status",
        "planned_withdrawal_schedules",
        ["quality_status"],
    )
    op.create_index(
        "ix_planned_withdrawal_schedule_window",
        "planned_withdrawal_schedules",
        ["portfolio_id", "client_id", "scheduled_date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_planned_withdrawal_schedule_window", table_name="planned_withdrawal_schedules"
    )
    op.drop_index(
        "ix_planned_withdrawal_schedules_quality_status", table_name="planned_withdrawal_schedules"
    )
    op.drop_index(
        "ix_planned_withdrawal_schedules_purpose_code", table_name="planned_withdrawal_schedules"
    )
    op.drop_index(
        "ix_planned_withdrawal_schedules_recurrence_frequency",
        table_name="planned_withdrawal_schedules",
    )
    op.drop_index(
        "ix_planned_withdrawal_schedules_scheduled_date", table_name="planned_withdrawal_schedules"
    )
    op.drop_index(
        "ix_planned_withdrawal_schedules_currency", table_name="planned_withdrawal_schedules"
    )
    op.drop_index(
        "ix_planned_withdrawal_schedules_withdrawal_status",
        table_name="planned_withdrawal_schedules",
    )
    op.drop_index(
        "ix_planned_withdrawal_schedules_withdrawal_type", table_name="planned_withdrawal_schedules"
    )
    op.drop_index(
        "ix_planned_withdrawal_schedules_withdrawal_schedule_id",
        table_name="planned_withdrawal_schedules",
    )
    op.drop_index(
        "ix_planned_withdrawal_schedules_mandate_id", table_name="planned_withdrawal_schedules"
    )
    op.drop_index(
        "ix_planned_withdrawal_schedules_portfolio_id", table_name="planned_withdrawal_schedules"
    )
    op.drop_index(
        "ix_planned_withdrawal_schedules_client_id", table_name="planned_withdrawal_schedules"
    )
    op.drop_table("planned_withdrawal_schedules")
    op.drop_index(
        "ix_liquidity_reserve_requirement_effective_window",
        table_name="liquidity_reserve_requirements",
    )
    op.drop_index(
        "ix_liquidity_reserve_requirements_quality_status",
        table_name="liquidity_reserve_requirements",
    )
    op.drop_index(
        "ix_liquidity_reserve_requirements_effective_to",
        table_name="liquidity_reserve_requirements",
    )
    op.drop_index(
        "ix_liquidity_reserve_requirements_effective_from",
        table_name="liquidity_reserve_requirements",
    )
    op.drop_index(
        "ix_liquidity_reserve_requirements_currency", table_name="liquidity_reserve_requirements"
    )
    op.drop_index(
        "ix_liquidity_reserve_requirements_reserve_status",
        table_name="liquidity_reserve_requirements",
    )
    op.drop_index(
        "ix_liquidity_reserve_requirements_reserve_type",
        table_name="liquidity_reserve_requirements",
    )
    op.drop_index(
        "ix_liquidity_reserve_requirements_reserve_requirement_id",
        table_name="liquidity_reserve_requirements",
    )
    op.drop_index(
        "ix_liquidity_reserve_requirements_mandate_id", table_name="liquidity_reserve_requirements"
    )
    op.drop_index(
        "ix_liquidity_reserve_requirements_portfolio_id",
        table_name="liquidity_reserve_requirements",
    )
    op.drop_index(
        "ix_liquidity_reserve_requirements_client_id", table_name="liquidity_reserve_requirements"
    )
    op.drop_table("liquidity_reserve_requirements")
    op.drop_index(
        "ix_client_income_needs_schedule_effective_window",
        table_name="client_income_needs_schedules",
    )
    op.drop_index(
        "ix_client_income_needs_schedules_quality_status",
        table_name="client_income_needs_schedules",
    )
    op.drop_index(
        "ix_client_income_needs_schedules_end_date", table_name="client_income_needs_schedules"
    )
    op.drop_index(
        "ix_client_income_needs_schedules_start_date", table_name="client_income_needs_schedules"
    )
    op.drop_index(
        "ix_client_income_needs_schedules_frequency", table_name="client_income_needs_schedules"
    )
    op.drop_index(
        "ix_client_income_needs_schedules_currency", table_name="client_income_needs_schedules"
    )
    op.drop_index(
        "ix_client_income_needs_schedules_need_status", table_name="client_income_needs_schedules"
    )
    op.drop_index(
        "ix_client_income_needs_schedules_need_type", table_name="client_income_needs_schedules"
    )
    op.drop_index(
        "ix_client_income_needs_schedules_schedule_id", table_name="client_income_needs_schedules"
    )
    op.drop_index(
        "ix_client_income_needs_schedules_mandate_id", table_name="client_income_needs_schedules"
    )
    op.drop_index(
        "ix_client_income_needs_schedules_portfolio_id", table_name="client_income_needs_schedules"
    )
    op.drop_index(
        "ix_client_income_needs_schedules_client_id", table_name="client_income_needs_schedules"
    )
    op.drop_table("client_income_needs_schedules")
