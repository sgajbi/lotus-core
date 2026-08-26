"""Harden durable reprocessing payload integrity.

Revision ID: c162b2c3d529
Revises: c161b2c3d528
Create Date: 2026-08-26
"""

from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "c162b2c3d529"
down_revision: str | Sequence[str] | None = "c161b2c3d528"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE_NAME = "reprocessing_jobs"
_ACTIVE_PAYLOAD_CONSTRAINT = "ck_reprocessing_jobs_active_payload_valid"
_TEMPORAL_QUARANTINE_TABLE = "c162_invalid_temporal_reprocessing_jobs"
_PAYLOAD_PREFLIGHT = sa.text(
    r"""
    DO $$
    DECLARE
        unsafe_json_count bigint;
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
    END
    $$
    """
)
_PAYLOAD_CUTOVER = sa.text(
    r"""
    DO $$
    DECLARE
        quarantined_fx_count bigint;
        quarantined_security_count bigint;
    BEGIN

        UPDATE reprocessing_jobs
        SET status = 'FAILED',
            failure_reason = (
                'invalid_reprocessing_job_payload: quarantined during contract cutover'
            ),
            updated_at = now()
        WHERE job_type = 'RESET_FX_WATERMARKS'
          AND status = 'PENDING'
          AND (
              id IN (SELECT id FROM pg_temp.c162_invalid_temporal_reprocessing_jobs)
              OR jsonb_typeof(payload::jsonb->'from_currency') IS DISTINCT FROM 'string'
              OR jsonb_typeof(payload::jsonb->'to_currency') IS DISTINCT FROM 'string'
              OR jsonb_typeof(payload::jsonb->'content_hash') IS DISTINCT FROM 'string'
              OR jsonb_typeof(
                  payload::jsonb->'earliest_impacted_date'
              ) IS DISTINCT FROM 'string'
              OR jsonb_typeof(payload::jsonb->'generated_at') IS DISTINCT FROM 'string'
              OR nullif(btrim(payload->>'from_currency'), '') IS NULL
              OR nullif(btrim(payload->>'to_currency'), '') IS NULL
              OR nullif(btrim(payload->>'content_hash'), '') IS NULL
              OR payload->>'from_currency' <> btrim(payload->>'from_currency')
              OR payload->>'to_currency' <> btrim(payload->>'to_currency')
              OR payload->>'content_hash' <> btrim(payload->>'content_hash')
              OR pg_input_is_valid(
                  payload->>'earliest_impacted_date', 'date'
              ) IS NOT TRUE
              OR pg_input_is_valid(
                  payload->>'generated_at', 'timestamp with time zone'
              ) IS NOT TRUE
              OR payload->>'generated_at' !~ (
                  '(Z|[+-][0-9]{2}(:?[0-9]{2}'
                  '(:?[0-9]{2}([.][0-9]+)?)?)?)$'
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
              id IN (SELECT id FROM pg_temp.c162_invalid_temporal_reprocessing_jobs)
              OR jsonb_typeof(payload::jsonb->'security_id') IS DISTINCT FROM 'string'
              OR jsonb_typeof(
                  payload::jsonb->'earliest_impacted_date'
              ) IS DISTINCT FROM 'string'
              OR nullif(btrim(payload->>'security_id'), '') IS NULL
              OR payload->>'security_id' <> btrim(payload->>'security_id')
              OR pg_input_is_valid(
                  payload->>'earliest_impacted_date', 'date'
              ) IS NOT TRUE
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

    op.execute(_PAYLOAD_PREFLIGHT)
    _stage_python_temporal_quarantine(op.get_bind())
    op.execute(_PAYLOAD_CUTOVER)
    op.create_check_constraint(
        _ACTIVE_PAYLOAD_CONSTRAINT,
        _TABLE_NAME,
        """
        CASE
            WHEN status NOT IN ('PENDING', 'PROCESSING') THEN TRUE
            WHEN job_type NOT IN ('RESET_FX_WATERMARKS', 'RESET_WATERMARKS') THEN TRUE
            WHEN pg_input_is_valid(payload::text, 'jsonb') IS NOT TRUE THEN FALSE
            WHEN job_type = 'RESET_FX_WATERMARKS' THEN (
                jsonb_typeof(payload::jsonb->'from_currency') = 'string'
                AND jsonb_typeof(payload::jsonb->'to_currency') = 'string'
                AND jsonb_typeof(payload::jsonb->'content_hash') = 'string'
                AND jsonb_typeof(payload::jsonb->'earliest_impacted_date') = 'string'
                AND jsonb_typeof(payload::jsonb->'generated_at') = 'string'
                AND nullif(btrim(payload->>'from_currency'), '') IS NOT NULL
                AND nullif(btrim(payload->>'to_currency'), '') IS NOT NULL
                AND nullif(btrim(payload->>'content_hash'), '') IS NOT NULL
                AND payload->>'from_currency' = btrim(payload->>'from_currency')
                AND payload->>'to_currency' = btrim(payload->>'to_currency')
                AND payload->>'content_hash' = btrim(payload->>'content_hash')
                AND pg_input_is_valid(payload->>'earliest_impacted_date', 'date') IS TRUE
                AND pg_input_is_valid(
                    payload->>'generated_at', 'timestamp with time zone'
                ) IS TRUE
                AND payload->>'generated_at' ~ (
                    '(Z|[+-][0-9]{2}(:?[0-9]{2}'
                    '(:?[0-9]{2}([.][0-9]+)?)?)?)$'
                )
            )
            WHEN job_type = 'RESET_WATERMARKS' THEN (
                jsonb_typeof(payload::jsonb->'security_id') = 'string'
                AND jsonb_typeof(payload::jsonb->'earliest_impacted_date') = 'string'
                AND nullif(btrim(payload->>'security_id'), '') IS NOT NULL
                AND payload->>'security_id' = btrim(payload->>'security_id')
                AND pg_input_is_valid(payload->>'earliest_impacted_date', 'date') IS TRUE
            )
            ELSE TRUE
        END
        """,
    )


def _stage_python_temporal_quarantine(bind: Any) -> None:
    """Snapshot Python's ISO grammar under the cutover lock without importing mutable app code."""

    op.execute(
        sa.text(
            f"""
            CREATE TEMPORARY TABLE IF NOT EXISTS {_TEMPORAL_QUARANTINE_TABLE} (
                id bigint PRIMARY KEY
            ) ON COMMIT DROP;
            TRUNCATE TABLE {_TEMPORAL_QUARANTINE_TABLE}
            """
        )
    )
    rows = bind.execute(
        sa.text(
            """
            SELECT id, job_type, payload
            FROM reprocessing_jobs
            WHERE status = 'PENDING'
              AND job_type IN ('RESET_FX_WATERMARKS', 'RESET_WATERMARKS')
            ORDER BY id
            """
        )
    ).mappings()
    invalid_ids = [
        int(row["id"])
        for row in rows
        if not _has_valid_temporal_grammar(
            job_type=str(row["job_type"]),
            payload=row["payload"],
        )
    ]
    if invalid_ids:
        bind.execute(
            sa.text(f"INSERT INTO {_TEMPORAL_QUARANTINE_TABLE} (id) VALUES (:id)"),
            [{"id": job_id} for job_id in invalid_ids],
        )


def _has_valid_temporal_grammar(*, job_type: str, payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    try:
        impacted = payload.get("earliest_impacted_date")
        if not isinstance(impacted, str):
            return False
        date.fromisoformat(impacted)
        if job_type == "RESET_FX_WATERMARKS":
            generated = payload.get("generated_at")
            if not isinstance(generated, str):
                return False
            generated_at = datetime.fromisoformat(generated)
            if generated_at.tzinfo is None or generated_at.utcoffset() is None:
                return False
    except (TypeError, ValueError):
        return False
    return True


def downgrade() -> None:
    """Remove active payload enforcement without rewriting replay evidence."""

    op.drop_constraint(_ACTIVE_PAYLOAD_CONSTRAINT, _TABLE_NAME, type_="check")
