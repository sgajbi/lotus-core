"""Guard and quarantine retained effective-dated replay payloads before SQL casts."""

from collections.abc import Callable, Mapping
from datetime import date
from typing import Any

from sqlalchemy import String, bindparam, func, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from .database_models import ReprocessingJob
from .infrastructure.persistence.statement_batching import (
    StatementBatchOperation,
    iter_statement_chunks,
    observe_multi_statement_batch,
)

REPLAY_TEXT_TRIM_CHARS = (
    "\u0009\u000a\u000b\u000c\u000d\u001c\u001d\u001e\u001f\u0020\u0085\u00a0\u1680"
    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029"
    "\u202f\u205f\u3000"
)
PYTHON_ISO_DATE_PATTERN = (
    r"^([0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{8}|"
    r"[0-9]{4}-W[0-9]{2}(-[1-7])?|[0-9]{4}W[0-9]{2}[1-7]?)$"
)

NORMALIZE_PENDING_RESET_WATERMARKS = text(
    """
    WITH valid_candidates AS MATERIALIZED (
        SELECT
            id,
            btrim(payload->>'security_id', :trim_chars) AS security_id,
            payload,
            payload->>'earliest_impacted_date' AS earliest_impacted_date,
            created_at
        FROM reprocessing_jobs
        WHERE status = 'PENDING'
          AND job_type = 'RESET_WATERMARKS'
          AND CASE
              WHEN pg_input_is_valid(payload::text, 'jsonb') IS NOT TRUE THEN FALSE
              WHEN json_typeof(payload->'security_id') IS DISTINCT FROM 'string' THEN FALSE
              WHEN json_typeof(payload->'earliest_impacted_date') IS DISTINCT FROM 'string'
              THEN FALSE
              WHEN payload->>'earliest_impacted_date' !~ :python_iso_date_pattern THEN FALSE
              ELSE btrim(payload->>'security_id', :trim_chars) <> ''
               AND pg_input_is_valid(payload->>'earliest_impacted_date', 'date')
          END
    ),
    ranked AS (
        SELECT
            id,
            security_id,
            earliest_impacted_date::date AS earliest_impacted_date,
            row_number() OVER (
                PARTITION BY security_id
                ORDER BY earliest_impacted_date::date ASC, created_at ASC, id ASC
            ) AS rn,
            min(earliest_impacted_date::date) OVER (
                PARTITION BY security_id
            ) AS min_impacted_date
        FROM valid_candidates
    ),
    keepers AS (
        UPDATE reprocessing_jobs j
        SET payload = jsonb_set(
                jsonb_set(
                    j.payload::jsonb,
                    '{security_id}',
                    to_jsonb(r.security_id)
                ),
                '{earliest_impacted_date}',
                to_jsonb(r.min_impacted_date::text)
            )::json,
            updated_at = now()
        FROM ranked r
        WHERE j.id = r.id
          AND r.rn = 1
          AND (
              j.payload->>'security_id' IS DISTINCT FROM r.security_id
              OR (j.payload->>'earliest_impacted_date')::date <> r.min_impacted_date
          )
        RETURNING j.id
    ),
    deleted AS (
        DELETE FROM reprocessing_jobs j
        USING ranked r
        WHERE j.id = r.id
          AND r.rn > 1
        RETURNING j.id
    )
    SELECT count(*) FROM deleted;
    """
).bindparams(bindparam("python_iso_date_pattern", value=PYTHON_ISO_DATE_PATTERN))

PENDING_FX_REPLAY_CANDIDATES = text(
    """
    SELECT
        id,
        payload,
        pg_input_is_valid(payload::text, 'jsonb') AS payload_representable,
        CASE
            WHEN pg_input_is_valid(payload::text, 'jsonb') IS NOT TRUE THEN FALSE
            WHEN json_typeof(payload->'earliest_impacted_date') IS DISTINCT FROM 'string'
            THEN FALSE
            ELSE pg_input_is_valid(payload->>'earliest_impacted_date', 'date')
        END AS earliest_date_representable,
        CASE
            WHEN pg_input_is_valid(payload::text, 'jsonb') IS NOT TRUE THEN FALSE
            WHEN json_typeof(payload->'generated_at') IS DISTINCT FROM 'string'
            THEN FALSE
            ELSE pg_input_is_valid(
                payload->>'generated_at', 'timestamp with time zone'
            )
        END AS generated_at_representable
    FROM reprocessing_jobs
    WHERE job_type = 'RESET_FX_WATERMARKS'
      AND status = 'PENDING'
      AND btrim(payload->>'from_currency', :trim_chars) = :from_currency
      AND btrim(payload->>'to_currency', :trim_chars) = :to_currency
    FOR UPDATE
    """
).bindparams(
    bindparam("from_currency", type_=String()),
    bindparam("to_currency", type_=String()),
    bindparam("trim_chars", type_=String()),
)

PENDING_RESET_REPLAY_CANDIDATES = text(
    """
    SELECT
        id,
        payload,
        pg_input_is_valid(payload::text, 'jsonb') AS payload_representable,
        CASE
            WHEN pg_input_is_valid(payload::text, 'jsonb') IS NOT TRUE THEN FALSE
            WHEN json_typeof(payload->'earliest_impacted_date') IS DISTINCT FROM 'string'
            THEN FALSE
            ELSE pg_input_is_valid(payload->>'earliest_impacted_date', 'date')
        END AS earliest_date_representable
    FROM reprocessing_jobs
    WHERE job_type = 'RESET_WATERMARKS'
      AND status = 'PENDING'
      AND btrim(payload->>'security_id', :trim_chars) = :security_id
    FOR UPDATE
    """
).bindparams(
    bindparam("security_id", type_=String()),
    bindparam("trim_chars", type_=String()),
)

PENDING_RESET_REPLAY_SIBLING = text(
    """
    SELECT id
    FROM reprocessing_jobs
    WHERE id <> :job_id
      AND job_type = 'RESET_WATERMARKS'
      AND status = 'PENDING'
      AND btrim(payload->>'security_id', :trim_chars) = :security_id
    ORDER BY id
    LIMIT 1
    FOR UPDATE
    """
)

PENDING_FX_REPLAY_SIBLING = text(
    """
    SELECT id
    FROM reprocessing_jobs
    WHERE id <> :job_id
      AND job_type = 'RESET_FX_WATERMARKS'
      AND status = 'PENDING'
      AND btrim(payload->>'from_currency', :trim_chars) = :from_currency
      AND btrim(payload->>'to_currency', :trim_chars) = :to_currency
    ORDER BY id
    LIMIT 1
    FOR UPDATE
    """
)


async def quarantine_pending_fx_pair(
    db: AsyncSession,
    *,
    from_currency: str,
    to_currency: str,
    validate: Callable[[object], object],
    parse_earliest_date: Callable[[object], date | None],
) -> date | None:
    """Quarantine malformed retained FX work and return its usable earliest boundary."""

    result = await db.execute(
        PENDING_FX_REPLAY_CANDIDATES,
        {
            "from_currency": from_currency,
            "to_currency": to_currency,
            "trim_chars": REPLAY_TEXT_TRIM_CHARS,
        },
    )
    return await _quarantine_candidates(
        db,
        rows=result.mappings().all(),
        required_validity_fields=(
            "payload_representable",
            "earliest_date_representable",
            "generated_at_representable",
        ),
        validate=validate,
        parse_earliest_date=parse_earliest_date,
        failure_reason="invalid_fx_revaluation_job_payload: superseded during valid replay staging",
    )


async def quarantine_pending_reset_security(
    db: AsyncSession,
    *,
    security_id: str,
    validate: Callable[[object], object],
    parse_earliest_date: Callable[[object], date | None],
) -> date | None:
    """Quarantine malformed retained security work and return its usable earliest boundary."""

    result = await db.execute(
        PENDING_RESET_REPLAY_CANDIDATES,
        {
            "security_id": security_id,
            "trim_chars": REPLAY_TEXT_TRIM_CHARS,
        },
    )
    return await _quarantine_candidates(
        db,
        rows=result.mappings().all(),
        required_validity_fields=("payload_representable", "earliest_date_representable"),
        validate=validate,
        parse_earliest_date=parse_earliest_date,
        failure_reason=(
            "invalid_reset_watermarks_job_payload: superseded during valid replay staging"
        ),
    )


async def _quarantine_candidates(
    db: AsyncSession,
    *,
    rows: list[Mapping[str, Any]],
    required_validity_fields: tuple[str, ...],
    validate: Callable[[object], object],
    parse_earliest_date: Callable[[object], date | None],
    failure_reason: str,
) -> date | None:
    malformed_ids: list[int] = []
    known_earliest_dates: list[date] = []
    for row in rows:
        payload = row["payload"]
        try:
            if not all(row[field] for field in required_validity_fields):
                raise ValueError("replay payload is not PostgreSQL-representable")
            validate(payload)
        except (TypeError, ValueError):
            malformed_ids.append(int(row["id"]))
            if (earliest_date := parse_earliest_date(payload)) is not None:
                known_earliest_dates.append(earliest_date)

    if malformed_ids:
        observe_multi_statement_batch(
            operation=StatementBatchOperation.REPROCESSING_INVALID_PAYLOAD_UPDATE,
            item_count=len(malformed_ids),
            binds_per_row=1,
            reserved_binds=2,
        )
        for malformed_id_chunk in iter_statement_chunks(
            malformed_ids,
            binds_per_row=1,
            reserved_binds=2,
        ):
            await db.execute(
                update(ReprocessingJob)
                .where(ReprocessingJob.id.in_(malformed_id_chunk))
                .values(
                    status="FAILED",
                    failure_reason=failure_reason,
                    updated_at=func.now(),
                )
            )
    return min(known_earliest_dates, default=None)
