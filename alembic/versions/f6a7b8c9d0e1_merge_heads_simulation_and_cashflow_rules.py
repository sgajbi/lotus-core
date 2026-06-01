"""merge heads after simulation session migration

Revision ID: f6a7b8c9d0e1
Revises: 1a7b8c9d0e2f, e3f4a5b6c7d8
Create Date: 2026-02-24 11:46:00.000000

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = ("1a7b8c9d0e2f", "e3f4a5b6c7d8")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # merge migration: no schema changes
    pass


def downgrade() -> None:
    # merge migration: no schema changes
    pass
