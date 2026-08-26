"""Harden durable reprocessing payload integrity.

Revision ID: c162b2c3d529
Revises: c161b2c3d528
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c162b2c3d529"
down_revision: str | Sequence[str] | None = "c161b2c3d528"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE_NAME = "reprocessing_jobs"
_ACTIVE_PAYLOAD_CONSTRAINT = "ck_reprocessing_jobs_active_payload_valid"
_PAYLOAD_CUTOVER = sa.text(
    r"""
    DO $$
    DECLARE
        unsafe_json_count bigint;
        quarantined_fx_count bigint;
        quarantined_security_count bigint;
    BEGIN
        PERFORM set_config('lock_timeout', '5s', true);
        LOCK TABLE reprocessing_jobs IN ACCESS EXCLUSIVE MODE;

        SELECT count(*)
        INTO unsafe_json_count
        FROM reprocessing_jobs
        WHERE status IN ('PENDING', 'PROCESSING')
          AND job_type IN ('RESET_FX_WATERMARKS', 'RESET_WATERMARKS')
          AND pg_input_is_valid(payload::text, 'jsonb') IS NOT TRUE;

        IF unsafe_json_count > 0 THEN
            RAISE EXCEPTION USING
                MESSAGE = format(
                    'reprocessing payload cutover found %s active row(s) that cannot '
                    'be safely extracted',
                    unsafe_json_count
                ),
                HINT = (
                    'preserve the raw payload evidence and terminalize or repair the affected '
                    'rows through a governed recovery before retrying the migration'
                );
        END IF;

        IF EXISTS (
            SELECT 1 FROM reprocessing_jobs WHERE status = 'PROCESSING'
        ) THEN
            RAISE EXCEPTION USING
                MESSAGE = 'reprocessing payload cutover requires a drained PROCESSING queue',
                HINT = 'pause the worker, recover or terminalize in-flight rows, then retry';
        END IF;

        UPDATE reprocessing_jobs
        SET status = 'FAILED',
            failure_reason = (
                'invalid_reprocessing_job_payload: quarantined during contract cutover'
            ),
            updated_at = now()
        WHERE job_type = 'RESET_FX_WATERMARKS'
          AND status = 'PENDING'
          AND (
              nullif(btrim(payload->>'from_currency'), '') IS NULL
              OR nullif(btrim(payload->>'to_currency'), '') IS NULL
              OR nullif(btrim(payload->>'content_hash'), '') IS NULL
              OR pg_input_is_valid(
                  payload->>'earliest_impacted_date', 'date'
              ) IS NOT TRUE
              OR payload->>'earliest_impacted_date' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
              OR pg_input_is_valid(
                  payload->>'generated_at', 'timestamp with time zone'
              ) IS NOT TRUE
              OR payload->>'generated_at' !~ (
                  '^[0-9]{4}-[0-9]{2}-[0-9]{2}T'
                  '[0-9]{2}:[0-9]{2}:[0-9]{2}([.][0-9]+)?'
                  '(Z|[+-][0-9]{2}(:?[0-9]{2})?)$'
              )
          );
        GET DIAGNOSTICS quarantined_fx_count = ROW_COUNT;

        UPDATE reprocessing_jobs
        SET status = 'FAILED',
            failure_reason = (
                'invalid_reprocessing_job_payload: quarantined during contract cutover'
            ),
            updated_at = now()
        WHERE job_type = 'RESET_WATERMARKS'
          AND status = 'PENDING'
          AND (
              nullif(btrim(payload->>'security_id'), '') IS NULL
              OR pg_input_is_valid(
                  payload->>'earliest_impacted_date', 'date'
              ) IS NOT TRUE
              OR payload->>'earliest_impacted_date' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
          );
        GET DIAGNOSTICS quarantined_security_count = ROW_COUNT;

        RAISE NOTICE
            'reprocessing payload contract quarantined % FX and % security replay row(s)',
            quarantined_fx_count,
            quarantined_security_count;
    END
    $$
    """
)


def upgrade() -> None:
    """Quarantine invalid pending work and enforce the active payload contract."""

    op.execute(_PAYLOAD_CUTOVER)
    op.create_check_constraint(
        _ACTIVE_PAYLOAD_CONSTRAINT,
        _TABLE_NAME,
        """
        status NOT IN ('PENDING', 'PROCESSING')
        OR job_type NOT IN ('RESET_FX_WATERMARKS', 'RESET_WATERMARKS')
        OR (
            job_type = 'RESET_FX_WATERMARKS'
            AND nullif(btrim(payload->>'from_currency'), '') IS NOT NULL
            AND nullif(btrim(payload->>'to_currency'), '') IS NOT NULL
            AND nullif(btrim(payload->>'content_hash'), '') IS NOT NULL
            AND pg_input_is_valid(payload->>'earliest_impacted_date', 'date') IS TRUE
            AND payload->>'earliest_impacted_date' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
            AND pg_input_is_valid(
                payload->>'generated_at', 'timestamp with time zone'
            ) IS TRUE
            AND payload->>'generated_at' ~ (
                '^[0-9]{4}-[0-9]{2}-[0-9]{2}T'
                '[0-9]{2}:[0-9]{2}:[0-9]{2}([.][0-9]+)?'
                '(Z|[+-][0-9]{2}(:?[0-9]{2})?)$'
            )
        )
        OR (
            job_type = 'RESET_WATERMARKS'
            AND nullif(btrim(payload->>'security_id'), '') IS NOT NULL
            AND pg_input_is_valid(payload->>'earliest_impacted_date', 'date') IS TRUE
            AND payload->>'earliest_impacted_date' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
        )
        """,
    )


def downgrade() -> None:
    """Remove active payload enforcement without rewriting replay evidence."""

    op.drop_constraint(_ACTIVE_PAYLOAD_CONSTRAINT, _TABLE_NAME, type_="check")
