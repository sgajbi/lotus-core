"""Validate selected-history job checks without holding the column-add lock.

Revision ID: c172b2c3d533
Revises: c171b2c3d532
Create Date: 2026-09-21

The c171 NOT VALID checks protect new writes immediately. This revision validates
legacy rows after c171 is durably stamped, so a long scan does not extend the
ACCESS EXCLUSIVE lock from the column additions and a failed scan can be retried.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c172b2c3d533"
down_revision: str | Sequence[str] | None = "c171b2c3d532"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CHECKS = (
    (
        "ck_portfolio_aggregation_jobs_selected_history_sweep_epoch",
        "selected_history_sweep_epoch >= -1",
    ),
    (
        "ck_portfolio_aggregation_jobs_selected_history_collective_epoch",
        "selected_history_collective_epoch >= 0",
    ),
)


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for name, _condition in _CHECKS:
            op.execute(
                sa.text(f'ALTER TABLE portfolio_aggregation_jobs VALIDATE CONSTRAINT "{name}"')
            )


def downgrade() -> None:
    for name, condition in _CHECKS:
        op.drop_constraint(name, "portfolio_aggregation_jobs", type_="check")
        op.create_check_constraint(
            name,
            "portfolio_aggregation_jobs",
            condition,
            postgresql_not_valid=True,
        )
