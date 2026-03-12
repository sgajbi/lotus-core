"""feat: add pending reset-watermarks uniqueness

Revision ID: e4f5a6b7c8d9
Revises: d1e2f3a4b5c6
Create Date: 2026-03-12 18:15:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                payload->>'security_id' AS security_id,
                (payload->>'earliest_impacted_date')::date AS earliest_impacted_date,
                row_number() OVER (
                    PARTITION BY payload->>'security_id'
                    ORDER BY
                        (payload->>'earliest_impacted_date')::date ASC,
                        created_at ASC,
                        id ASC
                ) AS rn,
                min((payload->>'earliest_impacted_date')::date) OVER (
                    PARTITION BY payload->>'security_id'
                ) AS min_impacted_date
            FROM reprocessing_jobs
            WHERE status = 'PENDING' AND job_type = 'RESET_WATERMARKS'
        ),
        keepers AS (
            UPDATE reprocessing_jobs j
            SET payload = jsonb_set(
                    j.payload::jsonb,
                    '{earliest_impacted_date}',
                    to_jsonb(r.min_impacted_date::text)
                )::json,
                updated_at = now()
            FROM ranked r
            WHERE j.id = r.id
              AND r.rn = 1
              AND (j.payload->>'earliest_impacted_date')::date <> r.min_impacted_date
        )
        DELETE FROM reprocessing_jobs j
        USING ranked r
        WHERE j.id = r.id
          AND r.rn > 1;
        """
    )

    op.create_index(
        "uq_reprocessing_jobs_pending_reset_watermarks_security",
        "reprocessing_jobs",
        [sa.text("(payload->>'security_id')")],
        unique=True,
        postgresql_where=sa.text("job_type = 'RESET_WATERMARKS' AND status = 'PENDING'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_reprocessing_jobs_pending_reset_watermarks_security",
        table_name="reprocessing_jobs",
    )
