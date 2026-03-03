"""feat: add consumer DLQ reason-code taxonomy column

Revision ID: b7e8f9a0b1c2
Revises: a1d9c8b7e6f5
Create Date: 2026-03-03 14:15:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7e8f9a0b1c2"
down_revision: Union[str, None] = "a1d9c8b7e6f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "consumer_dlq_events",
        sa.Column(
            "error_reason_code",
            sa.String(),
            nullable=True,
            server_default="UNCLASSIFIED_PROCESSING_ERROR",
        ),
    )
    op.execute(
        "UPDATE consumer_dlq_events "
        "SET error_reason_code = 'UNCLASSIFIED_PROCESSING_ERROR' "
        "WHERE error_reason_code IS NULL"
    )
    op.alter_column("consumer_dlq_events", "error_reason_code", nullable=False)
    op.create_index(
        "ix_consumer_dlq_events_error_reason_code",
        "consumer_dlq_events",
        ["error_reason_code"],
    )


def downgrade() -> None:
    op.drop_index("ix_consumer_dlq_events_error_reason_code", table_name="consumer_dlq_events")
    op.drop_column("consumer_dlq_events", "error_reason_code")

