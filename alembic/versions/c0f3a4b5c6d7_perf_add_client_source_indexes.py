"""Add client source-data support indexes.

Revision ID: c0f3a4b5c6d7
Revises: c0f2a3b4c5d6
Create Date: 2026-05-31 11:35:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "c0f3a4b5c6d7"
down_revision = "c0f2a3b4c5d6"
branch_labels = None
depends_on = None


CLIENT_RESTRICTION_INDEX = "ix_client_restr_active_port_client_eff"
SUSTAINABILITY_PREFERENCE_INDEX = "ix_sust_pref_active_port_client_eff"
CLIENT_TAX_PROFILE_INDEX = "ix_client_tax_profile_active_eff"
CLIENT_TAX_RULE_INDEX = "ix_client_tax_rule_active_eff"
CLIENT_INCOME_NEEDS_INDEX = "ix_client_income_needs_active_eff"
LIQUIDITY_RESERVE_INDEX = "ix_liquidity_reserve_active_eff"
PLANNED_WITHDRAWAL_INDEX = "ix_planned_withdrawal_active_window"


def upgrade() -> None:
    op.execute(
        "UPDATE client_restriction_profiles "
        "SET restriction_status = lower(trim(restriction_status)) "
        "WHERE restriction_status IS NOT NULL"
    )
    op.execute(
        "UPDATE sustainability_preference_profiles "
        "SET preference_status = lower(trim(preference_status)) "
        "WHERE preference_status IS NOT NULL"
    )
    op.execute(
        "UPDATE client_tax_profiles "
        "SET profile_status = lower(trim(profile_status)) "
        "WHERE profile_status IS NOT NULL"
    )
    op.execute(
        "UPDATE client_tax_rule_sets "
        "SET rule_status = lower(trim(rule_status)) "
        "WHERE rule_status IS NOT NULL"
    )
    op.execute(
        "UPDATE client_income_needs_schedules "
        "SET need_status = lower(trim(need_status)) "
        "WHERE need_status IS NOT NULL"
    )
    op.execute(
        "UPDATE liquidity_reserve_requirements "
        "SET reserve_status = lower(trim(reserve_status)) "
        "WHERE reserve_status IS NOT NULL"
    )
    op.execute(
        "UPDATE planned_withdrawal_schedules "
        "SET withdrawal_status = lower(trim(withdrawal_status)) "
        "WHERE withdrawal_status IS NOT NULL"
    )
    op.create_index(
        CLIENT_RESTRICTION_INDEX,
        "client_restriction_profiles",
        [
            "portfolio_id",
            "client_id",
            "restriction_scope",
            "restriction_code",
            sa.text("effective_from DESC"),
            "effective_to",
            sa.text("observed_at DESC NULLS LAST"),
            sa.text("restriction_version DESC"),
            sa.text("updated_at DESC"),
        ],
        unique=False,
        postgresql_where=sa.text("restriction_status = 'active'"),
    )
    op.create_index(
        SUSTAINABILITY_PREFERENCE_INDEX,
        "sustainability_preference_profiles",
        [
            "portfolio_id",
            "client_id",
            "preference_framework",
            "preference_code",
            sa.text("effective_from DESC"),
            "effective_to",
            sa.text("observed_at DESC NULLS LAST"),
            sa.text("preference_version DESC"),
            sa.text("updated_at DESC"),
        ],
        unique=False,
        postgresql_where=sa.text("preference_status = 'active'"),
    )
    op.create_index(
        CLIENT_TAX_PROFILE_INDEX,
        "client_tax_profiles",
        [
            "portfolio_id",
            "client_id",
            "tax_profile_id",
            sa.text("effective_from DESC"),
            "effective_to",
            sa.text("observed_at DESC NULLS LAST"),
            sa.text("profile_version DESC"),
            sa.text("updated_at DESC"),
        ],
        unique=False,
        postgresql_where=sa.text("profile_status = 'active'"),
    )
    op.create_index(
        CLIENT_TAX_RULE_INDEX,
        "client_tax_rule_sets",
        [
            "portfolio_id",
            "client_id",
            "rule_set_id",
            "jurisdiction_code",
            "rule_code",
            sa.text("effective_from DESC"),
            "effective_to",
            sa.text("observed_at DESC NULLS LAST"),
            sa.text("rule_version DESC"),
            sa.text("updated_at DESC"),
        ],
        unique=False,
        postgresql_where=sa.text("rule_status = 'active'"),
    )
    op.create_index(
        CLIENT_INCOME_NEEDS_INDEX,
        "client_income_needs_schedules",
        [
            "portfolio_id",
            "client_id",
            "schedule_id",
            sa.text("start_date DESC"),
            "end_date",
            sa.text("observed_at DESC NULLS LAST"),
            sa.text("updated_at DESC"),
        ],
        unique=False,
        postgresql_where=sa.text("need_status = 'active'"),
    )
    op.create_index(
        LIQUIDITY_RESERVE_INDEX,
        "liquidity_reserve_requirements",
        [
            "portfolio_id",
            "client_id",
            "reserve_requirement_id",
            sa.text("effective_from DESC"),
            "effective_to",
            sa.text("observed_at DESC NULLS LAST"),
            sa.text("requirement_version DESC"),
            sa.text("updated_at DESC"),
        ],
        unique=False,
        postgresql_where=sa.text("reserve_status = 'active'"),
    )
    op.create_index(
        PLANNED_WITHDRAWAL_INDEX,
        "planned_withdrawal_schedules",
        [
            "portfolio_id",
            "client_id",
            "scheduled_date",
            "withdrawal_schedule_id",
            sa.text("observed_at DESC NULLS LAST"),
            sa.text("updated_at DESC"),
        ],
        unique=False,
        postgresql_where=sa.text("withdrawal_status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index(PLANNED_WITHDRAWAL_INDEX, table_name="planned_withdrawal_schedules")
    op.drop_index(LIQUIDITY_RESERVE_INDEX, table_name="liquidity_reserve_requirements")
    op.drop_index(CLIENT_INCOME_NEEDS_INDEX, table_name="client_income_needs_schedules")
    op.drop_index(CLIENT_TAX_RULE_INDEX, table_name="client_tax_rule_sets")
    op.drop_index(CLIENT_TAX_PROFILE_INDEX, table_name="client_tax_profiles")
    op.drop_index(SUSTAINABILITY_PREFERENCE_INDEX, table_name="sustainability_preference_profiles")
    op.drop_index(CLIENT_RESTRICTION_INDEX, table_name="client_restriction_profiles")
    # Client source-data lifecycle status canonicalization is intentionally irreversible.
