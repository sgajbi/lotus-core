"""Refuse reversed imported model windows without altering retained evidence.

Revision ID: c184b2c3d545
Revises: c183b2c3d544
"""

import sqlalchemy as sa

from alembic import op

revision = "c184b2c3d545"
down_revision = "c183b2c3d544"
branch_labels = None
depends_on = None

CONSTRAINTS = (
    ("model_portfolio_definitions", "ck_model_portfolio_definition_effective_window"),
    ("model_portfolio_targets", "ck_model_portfolio_target_effective_window"),
)
WINDOW = "effective_to IS NULL OR effective_to >= effective_from"


def upgrade() -> None:
    # Fence both source tables before preflight so an old writer cannot insert
    # a reversed window between inspection and constraint installation.
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(
        "LOCK TABLE model_portfolio_definitions, model_portfolio_targets IN ACCESS EXCLUSIVE MODE"
    )
    for table, _ in CONSTRAINTS:
        op.execute(
            sa.text(
                f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM {table} "
                "WHERE effective_to < effective_from) THEN "
                f"RAISE EXCEPTION 'MODEL_PORTFOLIO_INVALID_EFFECTIVE_WINDOW: {table}; "
                "retain rows and resolve source evidence before retry'; END IF; END $$"
            )
        )
    for table, name in CONSTRAINTS:
        op.create_check_constraint(name, table, WINDOW)


def downgrade() -> None:
    for table, name in reversed(CONSTRAINTS):
        op.drop_constraint(name, table, type_="check")
