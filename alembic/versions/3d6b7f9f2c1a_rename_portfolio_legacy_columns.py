"""rename portfolio legacy columns to canonical names

Revision ID: 3d6b7f9f2c1a
Revises: bfe95fef89d8
Create Date: 2026-02-27 14:38:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3d6b7f9f2c1a"
down_revision: Union[str, None] = "bfe95fef89d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {col["name"] for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    columns = _column_names("portfolios")

    if "booking_center" in columns and "booking_center_code" not in columns:
        op.alter_column("portfolios", "booking_center", new_column_name="booking_center_code")

    if "cif_id" in columns and "client_id" not in columns:
        op.alter_column("portfolios", "cif_id", new_column_name="client_id")

    op.execute("DROP INDEX IF EXISTS ix_portfolios_cif_id")
    op.execute("CREATE INDEX IF NOT EXISTS ix_portfolios_client_id ON portfolios (client_id)")


def downgrade() -> None:
    columns = _column_names("portfolios")

    if "booking_center_code" in columns and "booking_center" not in columns:
        op.alter_column("portfolios", "booking_center_code", new_column_name="booking_center")

    if "client_id" in columns and "cif_id" not in columns:
        op.alter_column("portfolios", "client_id", new_column_name="cif_id")

    op.execute("DROP INDEX IF EXISTS ix_portfolios_client_id")
    op.execute("CREATE INDEX IF NOT EXISTS ix_portfolios_cif_id ON portfolios (cif_id)")
