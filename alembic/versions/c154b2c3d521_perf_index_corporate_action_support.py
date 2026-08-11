"""Index bounded book-scoped corporate-action support queries.

Revision ID: c154b2c3d521
Revises: c153b2c3d520
"""

import sqlalchemy as sa

from alembic import op

revision = "c154b2c3d521"
down_revision = "c153b2c3d520"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_ca_event_book_scope_updated"
TABLE_NAME = "corporate_action_events"


def upgrade() -> None:
    op.create_index(
        INDEX_NAME,
        TABLE_NAME,
        [
            "tenant_id",
            "legal_book_id",
            "portfolio_id",
            sa.text("updated_at DESC"),
            sa.text("id DESC"),
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name=TABLE_NAME)
