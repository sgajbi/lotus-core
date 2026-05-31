"""Add normalized instrument eligibility support index.

Revision ID: c0fcd4e5f6a7
Revises: c0fcc3d4e5f6
Create Date: 2026-05-31 16:10:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "c0fcd4e5f6a7"
down_revision = "c0fcc3d4e5f6"
branch_labels = None
depends_on = None


INSTRUMENT_ELIGIBILITY_NORM_INDEX = "ix_instr_elig_norm_sec_eff"


def upgrade() -> None:
    op.create_index(
        INSTRUMENT_ELIGIBILITY_NORM_INDEX,
        "instrument_eligibility_profiles",
        [
            sa.text("trim(security_id)"),
            sa.text("effective_from DESC"),
            "effective_to",
            sa.text("observed_at DESC NULLS LAST"),
            sa.text("eligibility_version DESC"),
            sa.text("updated_at DESC"),
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        INSTRUMENT_ELIGIBILITY_NORM_INDEX,
        table_name="instrument_eligibility_profiles",
    )
