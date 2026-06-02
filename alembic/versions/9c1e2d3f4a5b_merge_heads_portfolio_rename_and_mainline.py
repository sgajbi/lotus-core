"""merge heads after portfolio legacy column rename

Revision ID: 9c1e2d3f4a5b
Revises: f6a7b8c9d0e1, 3d6b7f9f2c1a
Create Date: 2026-02-27 15:35:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "9c1e2d3f4a5b"
down_revision: Union[str, Sequence[str], None] = ("f6a7b8c9d0e1", "3d6b7f9f2c1a")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
