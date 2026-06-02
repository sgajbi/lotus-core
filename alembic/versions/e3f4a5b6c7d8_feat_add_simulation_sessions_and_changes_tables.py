"""feat: add simulation sessions and changes tables

Revision ID: e3f4a5b6c7d8
Revises: b25f9ec89ae3
Create Date: 2026-02-24 11:15:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, None] = "b25f9ec89ae3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "simulation_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("portfolio_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), server_default="ACTIVE", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.portfolio_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id"),
    )
    op.create_index(
        "ix_simulation_sessions_session_id", "simulation_sessions", ["session_id"], unique=True
    )
    op.create_index(
        "ix_simulation_sessions_portfolio_id", "simulation_sessions", ["portfolio_id"], unique=False
    )

    op.create_table(
        "simulation_changes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("change_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("portfolio_id", sa.String(), nullable=False),
        sa.Column("security_id", sa.String(), nullable=False),
        sa.Column("transaction_type", sa.String(), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 10), nullable=True),
        sa.Column("price", sa.Numeric(18, 10), nullable=True),
        sa.Column("amount", sa.Numeric(18, 10), nullable=True),
        sa.Column("currency", sa.String(), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["simulation_sessions.session_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("change_id"),
    )
    op.create_index(
        "ix_simulation_changes_change_id", "simulation_changes", ["change_id"], unique=True
    )
    op.create_index(
        "ix_simulation_changes_session_id", "simulation_changes", ["session_id"], unique=False
    )
    op.create_index(
        "ix_simulation_changes_portfolio_id", "simulation_changes", ["portfolio_id"], unique=False
    )
    op.create_index(
        "ix_simulation_changes_security_id", "simulation_changes", ["security_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_simulation_changes_security_id", table_name="simulation_changes")
    op.drop_index("ix_simulation_changes_portfolio_id", table_name="simulation_changes")
    op.drop_index("ix_simulation_changes_session_id", table_name="simulation_changes")
    op.drop_index("ix_simulation_changes_change_id", table_name="simulation_changes")
    op.drop_table("simulation_changes")

    op.drop_index("ix_simulation_sessions_portfolio_id", table_name="simulation_sessions")
    op.drop_index("ix_simulation_sessions_session_id", table_name="simulation_sessions")
    op.drop_table("simulation_sessions")
