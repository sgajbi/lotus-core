"""harden: add business-date calendar metadata and composite primary key

Revision ID: a1d9c8b7e6f5
Revises: 9f0a1b2c3d4e
Create Date: 2026-03-02 10:30:00
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1d9c8b7e6f5"
down_revision: Union[str, None] = "9f0a1b2c3d4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "business_dates",
        sa.Column("calendar_code", sa.String(), nullable=True, server_default="GLOBAL"),
    )
    op.add_column("business_dates", sa.Column("market_code", sa.String(), nullable=True))
    op.add_column("business_dates", sa.Column("source_system", sa.String(), nullable=True))
    op.add_column("business_dates", sa.Column("source_batch_id", sa.String(), nullable=True))

    op.execute("UPDATE business_dates SET calendar_code = 'GLOBAL' WHERE calendar_code IS NULL")
    op.alter_column("business_dates", "calendar_code", nullable=False)

    op.drop_constraint("business_dates_pkey", "business_dates", type_="primary")
    op.create_primary_key("business_dates_pkey", "business_dates", ["calendar_code", "date"])


def downgrade() -> None:
    op.drop_constraint("business_dates_pkey", "business_dates", type_="primary")
    op.create_primary_key("business_dates_pkey", "business_dates", ["date"])

    op.drop_column("business_dates", "source_batch_id")
    op.drop_column("business_dates", "source_system")
    op.drop_column("business_dates", "market_code")
    op.drop_column("business_dates", "calendar_code")

