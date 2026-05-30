"""Add DPM mandate source-data support index.

Revision ID: c0f1a2b3c4d5
Revises: c0f0a1b2c3d4
Create Date: 2026-05-31 10:20:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "c0f1a2b3c4d5"
down_revision = "c0f0a1b2c3d4"
branch_labels = None
depends_on = None


INDEX_NAME = "ix_mandate_binding_dpm_model_book_eff"


def upgrade() -> None:
    op.execute(
        "UPDATE portfolio_mandate_bindings "
        "SET mandate_type = lower(trim(mandate_type)), "
        "discretionary_authority_status = lower(trim(discretionary_authority_status)) "
        "WHERE mandate_type IS NOT NULL OR discretionary_authority_status IS NOT NULL"
    )
    op.create_index(
        INDEX_NAME,
        "portfolio_mandate_bindings",
        [
            "model_portfolio_id",
            "booking_center_code",
            "effective_from",
            "effective_to",
            "portfolio_id",
            "mandate_id",
        ],
        unique=False,
        postgresql_where=sa.text(
            "mandate_type = 'discretionary' AND discretionary_authority_status = 'active'"
        ),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="portfolio_mandate_bindings")
    # Mandate type/status canonicalization is data cleanup and is intentionally irreversible.
