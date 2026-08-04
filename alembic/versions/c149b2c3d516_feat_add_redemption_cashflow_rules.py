"""Add canonical fixed-income redemption cashflow rules.

Revision ID: c149b2c3d516
Revises: c148b2c3d515
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c149b2c3d516"
down_revision: str | Sequence[str] | None = "c148b2c3d515"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Classify redemption proceeds as position-level investment inflows."""

    op.execute(
        sa.text(
            """
            INSERT INTO cashflow_rules (
                transaction_type,
                classification,
                timing,
                is_position_flow,
                is_portfolio_flow
            )
            VALUES
                ('MATURITY_REDEMPTION', 'INVESTMENT_INFLOW', 'EOD', true, false),
                ('CALL_REDEMPTION', 'INVESTMENT_INFLOW', 'EOD', true, false),
                ('PARTIAL_REDEMPTION', 'INVESTMENT_INFLOW', 'EOD', true, false)
            ON CONFLICT (transaction_type) DO UPDATE SET
                classification = EXCLUDED.classification,
                timing = EXCLUDED.timing,
                is_position_flow = EXCLUDED.is_position_flow,
                is_portfolio_flow = EXCLUDED.is_portfolio_flow,
                updated_at = now()
            """
        )
    )


def downgrade() -> None:
    """Remove rules for transaction types that return to production-disabled status."""

    op.execute(
        sa.text(
            """
            DELETE FROM cashflow_rules
            WHERE transaction_type IN (
                'MATURITY_REDEMPTION',
                'CALL_REDEMPTION',
                'PARTIAL_REDEMPTION'
            )
            """
        )
    )
