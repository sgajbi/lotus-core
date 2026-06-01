"""feat: add buy lot and accrued offset state

Revision ID: d4e5f6a7b8c9
Revises: c1d2e3f4a5b6
Create Date: 2026-02-28 12:45:00
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cashflows", sa.Column("economic_event_id", sa.String(), nullable=True))
    op.add_column(
        "cashflows", sa.Column("linked_transaction_group_id", sa.String(), nullable=True)
    )
    op.create_index(
        "ix_cashflows_economic_event_id",
        "cashflows",
        ["economic_event_id"],
        unique=False,
    )
    op.create_index(
        "ix_cashflows_linked_transaction_group_id",
        "cashflows",
        ["linked_transaction_group_id"],
        unique=False,
    )

    op.create_table(
        "position_lot_state",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("lot_id", sa.String(), nullable=False),
        sa.Column("source_transaction_id", sa.String(), nullable=False),
        sa.Column("portfolio_id", sa.String(), nullable=False),
        sa.Column("instrument_id", sa.String(), nullable=False),
        sa.Column("security_id", sa.String(), nullable=False),
        sa.Column("acquisition_date", sa.Date(), nullable=False),
        sa.Column("original_quantity", sa.Numeric(18, 10), nullable=False),
        sa.Column("open_quantity", sa.Numeric(18, 10), nullable=False),
        sa.Column("lot_cost_local", sa.Numeric(18, 10), nullable=False),
        sa.Column("lot_cost_base", sa.Numeric(18, 10), nullable=False),
        sa.Column(
            "accrued_interest_paid_local",
            sa.Numeric(18, 10),
            nullable=False,
            server_default="0",
        ),
        sa.Column("economic_event_id", sa.String(), nullable=True),
        sa.Column("linked_transaction_group_id", sa.String(), nullable=True),
        sa.Column("calculation_policy_id", sa.String(), nullable=True),
        sa.Column("calculation_policy_version", sa.String(), nullable=True),
        sa.Column("source_system", sa.String(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.portfolio_id"]),
        sa.ForeignKeyConstraint(["source_transaction_id"], ["transactions.transaction_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lot_id"),
        sa.UniqueConstraint("source_transaction_id"),
    )
    op.create_index(
        "ix_position_lot_state_lot_id", "position_lot_state", ["lot_id"], unique=False
    )
    op.create_index(
        "ix_position_lot_state_portfolio_id",
        "position_lot_state",
        ["portfolio_id"],
        unique=False,
    )
    op.create_index(
        "ix_position_lot_state_instrument_id",
        "position_lot_state",
        ["instrument_id"],
        unique=False,
    )
    op.create_index(
        "ix_position_lot_state_security_id",
        "position_lot_state",
        ["security_id"],
        unique=False,
    )
    op.create_index(
        "ix_position_lot_state_acquisition_date",
        "position_lot_state",
        ["acquisition_date"],
        unique=False,
    )
    op.create_index(
        "ix_position_lot_state_economic_event_id",
        "position_lot_state",
        ["economic_event_id"],
        unique=False,
    )
    op.create_index(
        "ix_position_lot_state_linked_transaction_group_id",
        "position_lot_state",
        ["linked_transaction_group_id"],
        unique=False,
    )

    op.create_table(
        "accrued_income_offset_state",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("offset_id", sa.String(), nullable=False),
        sa.Column("source_transaction_id", sa.String(), nullable=False),
        sa.Column("portfolio_id", sa.String(), nullable=False),
        sa.Column("instrument_id", sa.String(), nullable=False),
        sa.Column("security_id", sa.String(), nullable=False),
        sa.Column(
            "accrued_interest_paid_local",
            sa.Numeric(18, 10),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "remaining_offset_local",
            sa.Numeric(18, 10),
            nullable=False,
            server_default="0",
        ),
        sa.Column("economic_event_id", sa.String(), nullable=True),
        sa.Column("linked_transaction_group_id", sa.String(), nullable=True),
        sa.Column("calculation_policy_id", sa.String(), nullable=True),
        sa.Column("calculation_policy_version", sa.String(), nullable=True),
        sa.Column("source_system", sa.String(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.portfolio_id"]),
        sa.ForeignKeyConstraint(["source_transaction_id"], ["transactions.transaction_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("offset_id"),
        sa.UniqueConstraint("source_transaction_id"),
    )
    op.create_index(
        "ix_accrued_income_offset_state_offset_id",
        "accrued_income_offset_state",
        ["offset_id"],
        unique=False,
    )
    op.create_index(
        "ix_accrued_income_offset_state_portfolio_id",
        "accrued_income_offset_state",
        ["portfolio_id"],
        unique=False,
    )
    op.create_index(
        "ix_accrued_income_offset_state_instrument_id",
        "accrued_income_offset_state",
        ["instrument_id"],
        unique=False,
    )
    op.create_index(
        "ix_accrued_income_offset_state_security_id",
        "accrued_income_offset_state",
        ["security_id"],
        unique=False,
    )
    op.create_index(
        "ix_accrued_income_offset_state_economic_event_id",
        "accrued_income_offset_state",
        ["economic_event_id"],
        unique=False,
    )
    op.create_index(
        "ix_accrued_income_offset_state_linked_transaction_group_id",
        "accrued_income_offset_state",
        ["linked_transaction_group_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_accrued_income_offset_state_linked_transaction_group_id",
        table_name="accrued_income_offset_state",
    )
    op.drop_index(
        "ix_accrued_income_offset_state_economic_event_id",
        table_name="accrued_income_offset_state",
    )
    op.drop_index(
        "ix_accrued_income_offset_state_security_id",
        table_name="accrued_income_offset_state",
    )
    op.drop_index(
        "ix_accrued_income_offset_state_instrument_id",
        table_name="accrued_income_offset_state",
    )
    op.drop_index(
        "ix_accrued_income_offset_state_portfolio_id",
        table_name="accrued_income_offset_state",
    )
    op.drop_index(
        "ix_accrued_income_offset_state_offset_id",
        table_name="accrued_income_offset_state",
    )
    op.drop_table("accrued_income_offset_state")

    op.drop_index(
        "ix_position_lot_state_linked_transaction_group_id",
        table_name="position_lot_state",
    )
    op.drop_index(
        "ix_position_lot_state_economic_event_id",
        table_name="position_lot_state",
    )
    op.drop_index("ix_position_lot_state_acquisition_date", table_name="position_lot_state")
    op.drop_index("ix_position_lot_state_security_id", table_name="position_lot_state")
    op.drop_index("ix_position_lot_state_instrument_id", table_name="position_lot_state")
    op.drop_index("ix_position_lot_state_portfolio_id", table_name="position_lot_state")
    op.drop_index("ix_position_lot_state_lot_id", table_name="position_lot_state")
    op.drop_table("position_lot_state")

    op.drop_index("ix_cashflows_linked_transaction_group_id", table_name="cashflows")
    op.drop_index("ix_cashflows_economic_event_id", table_name="cashflows")
    op.drop_column("cashflows", "linked_transaction_group_id")
    op.drop_column("cashflows", "economic_event_id")
