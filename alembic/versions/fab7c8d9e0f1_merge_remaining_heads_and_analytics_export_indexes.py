"""merge remaining heads and analytics export indexes

Revision ID: fab7c8d9e0f1
Revises: 1a7b8c9d0e2f, e3f4a5b6c7d8, faa7b8c9d0e1
Create Date: 2026-03-13 21:20:00.000000
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "fab7c8d9e0f1"
down_revision: str | Sequence[str] | None = (
    "1a7b8c9d0e2f",
    "e3f4a5b6c7d8",
    "faa7b8c9d0e1",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
