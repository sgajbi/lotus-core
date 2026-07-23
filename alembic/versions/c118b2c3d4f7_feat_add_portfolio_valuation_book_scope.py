"""feat: add authoritative portfolio valuation-book scope

Revision ID: c118b2c3d4f7
Revises: c117b2c3d4f6
Create Date: 2026-07-23 15:15:00
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c118b2c3d4f7"
down_revision: Union[str, None] = "c117b2c3d4f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("portfolios", sa.Column("tenant_id", sa.String(), nullable=True))
    op.add_column("portfolios", sa.Column("legal_book_id", sa.String(), nullable=True))
    op.create_check_constraint(
        "ck_portfolios_valuation_book_scope_complete",
        "portfolios",
        "(tenant_id IS NULL AND legal_book_id IS NULL) OR "
        "(tenant_id IS NOT NULL AND legal_book_id IS NOT NULL "
        "AND tenant_id = btrim(tenant_id) AND legal_book_id = btrim(legal_book_id) "
        "AND tenant_id <> '' AND legal_book_id <> '')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_portfolios_valuation_book_scope_complete",
        "portfolios",
        type_="check",
    )
    op.drop_column("portfolios", "legal_book_id")
    op.drop_column("portfolios", "tenant_id")
