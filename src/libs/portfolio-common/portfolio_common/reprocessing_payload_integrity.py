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
REPLAY_CONTROL_PATTERN = r"[\u0001-\u001f\u007f-\u009f]"

QUARANTINE_PENDING_RESET_UNSAFE_IDENTITIES = text(
    """
    UPDATE reprocessing_jobs
    SET status = 'FAILED',
        failure_reason = 'invalid_reset_watermarks_job_payload: unsafe identity representation',
        updated_at = now()
    WHERE status = 'PENDING'
      AND job_type = 'RESET_WATERMARKS'
      AND CASE
          WHEN pg_input_is_valid(payload::text, 'jsonb') IS NOT TRUE THEN TRUE
          WHEN json_typeof(payload->'security_id') IS DISTINCT FROM 'string' THEN FALSE
          ELSE payload->>'security_id' ~ :replay_control_pattern
      END
    """
).bindparams(bindparam("replay_control_pattern", value=REPLAY_CONTROL_PATTERN))

PENDING_RESET_IDENTITY_LOCK_KEYS = text(
    """
    SELECT DISTINCT btrim(payload->>'security_id', :trim_chars) AS security_id
    FROM reprocessing_jobs
    WHERE status = 'PENDING'
      AND job_type = 'RESET_WATERMARKS'
      AND CASE
          WHEN pg_input_is_valid(payload::text, 'jsonb') IS NOT TRUE THEN FALSE
          WHEN json_typeof(payload->'security_id') IS DISTINCT FROM 'string' THEN FALSE
          WHEN payload->>'security_id' ~ :replay_control_pattern THEN FALSE
          ELSE btrim(payload->>'security_id', :trim_chars) <> ''
           AND payload->>'security_id'
               IS DISTINCT FROM btrim(payload->>'security_id', :trim_chars)
      END
    ORDER BY security_id
    """
).bindparams(bindparam("replay_control_pattern", value=REPLAY_CONTROL_PATTERN))
LOCK_EFFECTIVE_DATED_REPLAY_IDENTITY = text(
    "SELECT pg_advisory_xact_lock(hashtextextended(:identity_key, 0))"
)


def effective_dated_replay_identity_key(job_type: str, *components: str) -> str:
    """Encode one replay-family identity without delimiter ambiguity."""

    encoded_components = "|".join(f"{len(component)}:{component}" for component in components)
    return f"{job_type}|{encoded_components}"


QUARANTINE_PENDING_RESET_IDENTITY_COLLISIONS = text(
    """
    WITH valid_string_identities AS MATERIALIZED (
        SELECT DISTINCT btrim(payload->>'security_id', :trim_chars) AS security_id
        FROM reprocessing_jobs
        WHERE status = 'PENDING'
          AND job_type = 'RESET_WATERMARKS'
          AND CASE
              WHEN pg_input_is_valid(payload::text, 'jsonb') IS NOT TRUE THEN FALSE
              WHEN json_typeof(payload->'security_id') IS DISTINCT FROM 'string' THEN FALSE
              WHEN json_typeof(payload->'earliest_impacted_date') IS DISTINCT FROM 'string'
              THEN FALSE
              WHEN payload->>'security_id' ~ :replay_control_pattern THEN FALSE
              WHEN payload->>'earliest_impacted_date' !~ :python_iso_date_pattern THEN FALSE
              ELSE btrim(payload->>'security_id', :trim_chars) <> ''
               AND pg_input_is_valid(payload->>'earliest_impacted_date', 'date')
          END
    )
    UPDATE reprocessing_jobs AS collision
    SET status = 'FAILED',
        failure_reason = 'invalid_reset_watermarks_job_payload: identity collision',
        updated_at = now()
    FROM valid_string_identities AS valid
    WHERE collision.status = 'PENDING'
      AND collision.job_type = 'RESET_WATERMARKS'
      AND CASE
          WHEN pg_input_is_valid(collision.payload::text, 'jsonb') IS NOT TRUE THEN FALSE
          ELSE collision.payload->>'security_id' = valid.security_id
      END
      AND CASE
          WHEN pg_input_is_valid(collision.payload::text, 'jsonb') IS NOT TRUE THEN TRUE
          WHEN json_typeof(collision.payload->'security_id') IS DISTINCT FROM 'string' THEN TRUE
          WHEN json_typeof(collision.payload->'earliest_impacted_date') IS DISTINCT FROM 'string'
          THEN TRUE
          WHEN collision.payload->>'security_id' ~ :replay_control_pattern THEN TRUE
          WHEN collision.payload->>'earliest_impacted_date' !~ :python_iso_date_pattern THEN TRUE
          ELSE btrim(collision.payload->>'security_id', :trim_chars) = ''
            OR pg_input_is_valid(collision.payload->>'earliest_impacted_date', 'date') IS NOT TRUE
      END
    """
).bindparams(
    bindparam("python_iso_date_pattern", value=PYTHON_ISO_DATE_PATTERN),
    bindparam("replay_control_pattern", value=REPLAY_CONTROL_PATTERN),
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
              WHEN payload->>'security_id' ~ :replay_control_pattern THEN FALSE
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
).bindparams(
    bindparam("python_iso_date_pattern", value=PYTHON_ISO_DATE_PATTERN),
    bindparam("replay_control_pattern", value=REPLAY_CONTROL_PATTERN),
)


async def normalize_pending_reset_watermarks_duplicates(db: AsyncSession) -> int:
    """Quarantine unsafe identities, then serialize and coalesce valid repairs."""

    parameters = {"trim_chars": REPLAY_TEXT_TRIM_CHARS}
    identity_result = await db.execute(PENDING_RESET_IDENTITY_LOCK_KEYS, parameters)
    identity_keys = sorted(
        {
            effective_dated_replay_identity_key("RESET_WATERMARKS", str(security_id))
            for security_id in identity_result.scalars().all()
        }
    )
    for identity_key in identity_keys:
        await db.execute(
            LOCK_EFFECTIVE_DATED_REPLAY_IDENTITY,
            {"identity_key": identity_key},
        )
    await db.execute(QUARANTINE_PENDING_RESET_UNSAFE_IDENTITIES)
    await db.execute(QUARANTINE_PENDING_RESET_IDENTITY_COLLISIONS, parameters)
    result = await db.execute(NORMALIZE_PENDING_RESET_WATERMARKS, parameters)
    return int(result.scalar_one())


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
      AND CASE
          WHEN pg_input_is_valid(payload::text, 'jsonb') IS NOT TRUE THEN TRUE
          ELSE btrim(payload->>'from_currency', :trim_chars) = :from_currency
           AND btrim(payload->>'to_currency', :trim_chars) = :to_currency
      END
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
      AND CASE
          WHEN pg_input_is_valid(payload::text, 'jsonb') IS NOT TRUE THEN TRUE
          ELSE btrim(payload->>'security_id', :trim_chars) = :security_id
      END
    FOR UPDATE
    """
).bindparams(
    bindparam("security_id", type_=String()),
    bindparam("trim_chars", type_=String()),
)

PENDING_RESET_REPLAY_SIBLING = text(
    """
    SELECT id, payload
    FROM reprocessing_jobs
    WHERE id <> :job_id
      AND job_type = 'RESET_WATERMARKS'
      AND status = 'PENDING'
      AND CASE
          WHEN pg_input_is_valid(payload::text, 'jsonb') IS NOT TRUE THEN TRUE
          ELSE btrim(payload->>'security_id', :trim_chars) = :security_id
      END
    ORDER BY id
    FOR UPDATE
    """
)

PENDING_FX_REPLAY_SIBLING = text(
    """
    SELECT id, payload
    FROM reprocessing_jobs
    WHERE id <> :job_id
      AND job_type = 'RESET_FX_WATERMARKS'
      AND status = 'PENDING'
      AND CASE
          WHEN pg_input_is_valid(payload::text, 'jsonb') IS NOT TRUE THEN TRUE
          ELSE btrim(payload->>'from_currency', :trim_chars) = :from_currency
           AND btrim(payload->>'to_currency', :trim_chars) = :to_currency
      END
    ORDER BY id
    FOR UPDATE
    """
)


def replay_payload_matches_identity(
    payload: object,
    expected_identity: Mapping[str, str],
) -> bool:
    """Match an identity in Python when PostgreSQL cannot safely extract its JSON text."""

    if not isinstance(payload, Mapping):
        return False
    return all(
        isinstance(value := payload.get(field), str)
        and value.strip(REPLAY_TEXT_TRIM_CHARS) == expected
        for field, expected in expected_identity.items()
    )


async def pending_replay_sibling_exists(
    db: AsyncSession,
    *,
    job_id: int,
    job_type: str,
    payload: Mapping[str, Any],
) -> bool:
    """Lock and match a sibling without extracting an unsafe legacy JSON identity in SQL."""

    if job_type == "RESET_WATERMARKS":
        statement = PENDING_RESET_REPLAY_SIBLING
        expected_identity = {"security_id": str(payload["security_id"])}
    else:
        statement = PENDING_FX_REPLAY_SIBLING
        expected_identity = {
            "from_currency": str(payload["from_currency"]),
            "to_currency": str(payload["to_currency"]),
        }
    rows = (
        (
            await db.execute(
                statement,
                {"job_id": job_id, "trim_chars": REPLAY_TEXT_TRIM_CHARS, **expected_identity},
            )
        )
        .mappings()
        .all()
    )
    return any(replay_payload_matches_identity(row["payload"], expected_identity) for row in rows)


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
    expected_identity = {"from_currency": from_currency, "to_currency": to_currency}
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
        preserve_earliest_if=lambda payload: replay_payload_matches_identity(
            payload, expected_identity
        ),
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
    expected_identity = {"security_id": security_id}
    return await _quarantine_candidates(
        db,
        rows=result.mappings().all(),
        required_validity_fields=("payload_representable", "earliest_date_representable"),
        validate=validate,
        parse_earliest_date=parse_earliest_date,
        preserve_earliest_if=lambda payload: replay_payload_matches_identity(
            payload, expected_identity
        ),
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
    preserve_earliest_if: Callable[[object], bool] | None = None,
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
            if (preserve_earliest_if is None or preserve_earliest_if(payload)) and (
                earliest_date := parse_earliest_date(payload)
            ) is not None:
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
