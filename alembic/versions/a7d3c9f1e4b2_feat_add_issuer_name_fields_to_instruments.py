"""feat: add issuer name fields to instruments

Revision ID: a7d3c9f1e4b2
Revises: 9c1e2d3f4a5b
Create Date: 2026-02-27 11:30:00
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7d3c9f1e4b2"
down_revision: Union[str, None] = "9c1e2d3f4a5b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("instruments", sa.Column("issuer_name", sa.String(), nullable=True))
    op.add_column(
        "instruments",
        sa.Column("ultimate_parent_issuer_name", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("instruments", "ultimate_parent_issuer_name")
    op.drop_column("instruments", "issuer_name")
