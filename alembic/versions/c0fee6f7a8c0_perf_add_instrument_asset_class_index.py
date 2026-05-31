"""Add normalized instrument asset-class support index.

Revision ID: c0fee6f7a8c0
Revises: c0fde5f6a7b9
Create Date: 2026-05-31 21:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c0fee6f7a8c0"
down_revision: str | Sequence[str] | None = "c0fde5f6a7b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_instruments_norm_asset_cls_sec",
        "instruments",
        [sa.text("upper(trim(asset_class))"), sa.text("trim(security_id)")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_instruments_norm_asset_cls_sec", table_name="instruments")
