"""add cash account master and lookthrough tables

Revision ID: b1c2d3e4f5a6
Revises: rev_a1d9c8b7e6f5
Create Date: 2026-03-28 16:55:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "rev_a1d9c8b7e6f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cash_account_masters",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cash_account_id", sa.String(), nullable=False),
        sa.Column("portfolio_id", sa.String(), nullable=False),
        sa.Column("security_id", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("account_currency", sa.String(length=3), nullable=False),
        sa.Column("account_role", sa.String(), nullable=True),
        sa.Column(
            "lifecycle_status",
            sa.String(),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column("opened_on", sa.Date(), nullable=True),
        sa.Column("closed_on", sa.Date(), nullable=True),
        sa.Column("source_system", sa.String(), nullable=True),
        sa.Column("source_record_id", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.portfolio_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cash_account_id", name="_cash_account_master_id_uc"),
    )
    op.create_index(
        "ix_cash_account_masters_cash_account_id",
        "cash_account_masters",
        ["cash_account_id"],
        unique=False,
    )
    op.create_index(
        "ix_cash_account_masters_portfolio_id",
        "cash_account_masters",
        ["portfolio_id"],
        unique=False,
    )
    op.create_index(
        "ix_cash_account_masters_security_id",
        "cash_account_masters",
        ["security_id"],
        unique=False,
    )
    op.create_index(
        "ix_cash_account_masters_account_currency",
        "cash_account_masters",
        ["account_currency"],
        unique=False,
    )
    op.create_index(
        "ix_cash_account_masters_account_role",
        "cash_account_masters",
        ["account_role"],
        unique=False,
    )
    op.create_index(
        "ix_cash_account_masters_lifecycle_status",
        "cash_account_masters",
        ["lifecycle_status"],
        unique=False,
    )
    op.create_index(
        "ix_cash_account_masters_opened_on",
        "cash_account_masters",
        ["opened_on"],
        unique=False,
    )
    op.create_index(
        "ix_cash_account_masters_closed_on",
        "cash_account_masters",
        ["closed_on"],
        unique=False,
    )
    op.create_index(
        "ix_cash_account_master_portfolio_effective_window",
        "cash_account_masters",
        ["portfolio_id", "opened_on", "closed_on"],
        unique=False,
    )

    op.create_table(
        "instrument_lookthrough_components",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("parent_security_id", sa.String(), nullable=False),
        sa.Column("component_security_id", sa.String(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("component_weight", sa.Numeric(18, 10), nullable=False),
        sa.Column("source_system", sa.String(), nullable=True),
        sa.Column("source_record_id", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "parent_security_id",
            "component_security_id",
            "effective_from",
            name="_instrument_lookthrough_component_effective_uc",
        ),
    )
    op.create_index(
        "ix_instrument_lookthrough_components_parent_security_id",
        "instrument_lookthrough_components",
        ["parent_security_id"],
        unique=False,
    )
    op.create_index(
        "ix_instrument_lookthrough_components_component_security_id",
        "instrument_lookthrough_components",
        ["component_security_id"],
        unique=False,
    )
    op.create_index(
        "ix_instrument_lookthrough_components_effective_from",
        "instrument_lookthrough_components",
        ["effective_from"],
        unique=False,
    )
    op.create_index(
        "ix_instrument_lookthrough_components_effective_to",
        "instrument_lookthrough_components",
        ["effective_to"],
        unique=False,
    )
    op.create_index(
        "ix_instrument_lookthrough_parent_effective_window",
        "instrument_lookthrough_components",
        ["parent_security_id", "effective_from", "effective_to"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_instrument_lookthrough_parent_effective_window",
        table_name="instrument_lookthrough_components",
    )
    op.drop_index(
        "ix_instrument_lookthrough_components_effective_to",
        table_name="instrument_lookthrough_components",
    )
    op.drop_index(
        "ix_instrument_lookthrough_components_effective_from",
        table_name="instrument_lookthrough_components",
    )
    op.drop_index(
        "ix_instrument_lookthrough_components_component_security_id",
        table_name="instrument_lookthrough_components",
    )
    op.drop_index(
        "ix_instrument_lookthrough_components_parent_security_id",
        table_name="instrument_lookthrough_components",
    )
    op.drop_table("instrument_lookthrough_components")

    op.drop_index(
        "ix_cash_account_master_portfolio_effective_window",
        table_name="cash_account_masters",
    )
    op.drop_index("ix_cash_account_masters_closed_on", table_name="cash_account_masters")
    op.drop_index("ix_cash_account_masters_opened_on", table_name="cash_account_masters")
    op.drop_index(
        "ix_cash_account_masters_lifecycle_status", table_name="cash_account_masters"
    )
    op.drop_index("ix_cash_account_masters_account_role", table_name="cash_account_masters")
    op.drop_index(
        "ix_cash_account_masters_account_currency", table_name="cash_account_masters"
    )
    op.drop_index("ix_cash_account_masters_security_id", table_name="cash_account_masters")
    op.drop_index("ix_cash_account_masters_portfolio_id", table_name="cash_account_masters")
    op.drop_index(
        "ix_cash_account_masters_cash_account_id", table_name="cash_account_masters"
    )
    op.drop_table("cash_account_masters")
