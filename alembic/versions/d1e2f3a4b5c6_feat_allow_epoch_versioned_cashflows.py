"""feat: allow epoch-versioned cashflows per transaction

Revision ID: d1e2f3a4b5c6
Revises: be45fa67b890
Create Date: 2026-03-10 12:45:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "be45fa67b890"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint('_transaction_id_uc', 'cashflows', type_='unique')
    op.create_unique_constraint(
        '_transaction_epoch_uc',
        'cashflows',
        ['transaction_id', 'epoch'],
    )


def downgrade() -> None:
    op.drop_constraint('_transaction_epoch_uc', 'cashflows', type_='unique')
    op.create_unique_constraint('_transaction_id_uc', 'cashflows', ['transaction_id'])
