"""Guard and quarantine retained effective-dated replay payloads before SQL casts."""

import json
from collections.abc import Callable, Mapping
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, Integer, String, bindparam, func, text, update
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

PENDING_RESET_JSONB_INVALID_CANDIDATES = text(
    """
    SELECT
        id,
        payload::text AS payload_json,
        attempt_count,
        correlation_id,
        correlation_missing_reason,
        alternate_lookup_key
    FROM reprocessing_jobs
    WHERE status = 'PENDING'
      AND job_type = 'RESET_WATERMARKS'
      AND pg_input_is_valid(payload::text, 'jsonb') IS NOT TRUE
    ORDER BY id
    """
)

UPSERT_PENDING_RESET_WATERMARKS = text(
    """
    INSERT INTO reprocessing_jobs (
        job_type,
        payload,
        status,
        attempt_count,
        correlation_id,
        correlation_missing_reason,
        alternate_lookup_key
    )
    VALUES (
        'RESET_WATERMARKS',
        json_build_object(
            'security_id', :security_id,
            'earliest_impacted_date', :earliest_impacted_date
        )::json,
        'PENDING',
        :attempt_count,
        :correlation_id,
        :correlation_missing_reason,
        :alternate_lookup_key
    )
    ON CONFLICT ((payload->>'security_id'))
    WHERE job_type = 'RESET_WATERMARKS' AND status = 'PENDING'
    DO UPDATE
    SET payload = jsonb_set(
            reprocessing_jobs.payload::jsonb,
            '{earliest_impacted_date}',
            to_jsonb(
                LEAST(
                    (reprocessing_jobs.payload->>'earliest_impacted_date')::date,
                    CAST(:earliest_impacted_date AS date)
                )::text
            )
        )::json,
        attempt_count = GREATEST(
            reprocessing_jobs.attempt_count,
            EXCLUDED.attempt_count
        ),
        correlation_id = CASE
            WHEN CAST(:earliest_impacted_date AS date)
                 < (reprocessing_jobs.payload->>'earliest_impacted_date')::date
            THEN COALESCE(:correlation_id, reprocessing_jobs.correlation_id)
            WHEN reprocessing_jobs.correlation_id IS NULL
            THEN :correlation_id
            ELSE reprocessing_jobs.correlation_id
        END,
        correlation_missing_reason = CASE
            WHEN :correlation_id IS NOT NULL
            THEN NULL
            WHEN reprocessing_jobs.correlation_id IS NULL
                 AND CAST(:earliest_impacted_date AS date) <
                     CAST(reprocessing_jobs.payload->>'earliest_impacted_date' AS date)
            THEN :correlation_missing_reason
            WHEN reprocessing_jobs.correlation_id IS NULL
                 AND reprocessing_jobs.correlation_missing_reason IS NULL
            THEN :correlation_missing_reason
            ELSE reprocessing_jobs.correlation_missing_reason
        END,
        alternate_lookup_key = CASE
            WHEN :correlation_id IS NOT NULL
            THEN NULL
            WHEN reprocessing_jobs.correlation_id IS NULL
                 AND CAST(:earliest_impacted_date AS date) <
                     CAST(reprocessing_jobs.payload->>'earliest_impacted_date' AS date)
            THEN :alternate_lookup_key
            WHEN reprocessing_jobs.correlation_id IS NULL
                 AND reprocessing_jobs.alternate_lookup_key IS NULL
            THEN :alternate_lookup_key
            ELSE reprocessing_jobs.alternate_lookup_key
        END,
        updated_at = now()
    RETURNING *, (xmax = 0) AS was_inserted
    """
).bindparams(
    bindparam("security_id", type_=String()),
    bindparam("earliest_impacted_date", type_=Date()),
    bindparam("attempt_count", type_=Integer()),
    bindparam("correlation_id", type_=String()),
    bindparam("correlation_missing_reason", type_=String()),
    bindparam("alternate_lookup_key", type_=String()),
)

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
    invalid_rows = (await db.execute(PENDING_RESET_JSONB_INVALID_CANDIDATES)).mappings().all()
    recovery_plans = [
        plan for row in invalid_rows if (plan := _reset_boundary_recovery_plan(row)) is not None
    ]
    identity_result = await db.execute(PENDING_RESET_IDENTITY_LOCK_KEYS, parameters)
    identity_keys = sorted(
        {
            effective_dated_replay_identity_key("RESET_WATERMARKS", str(security_id))
            for security_id in identity_result.scalars().all()
        }
        | {plan["identity_key"] for plan in recovery_plans}
    )
    for identity_key in identity_keys:
        await db.execute(
            LOCK_EFFECTIVE_DATED_REPLAY_IDENTITY,
            {"identity_key": identity_key},
        )
    if recovery_plans:
        locked_rows = await _lock_scanned_replay_rows(
            db,
            candidate_ids=[int(plan["id"]) for plan in recovery_plans],
            job_type="RESET_WATERMARKS",
        )
        recovery_plans = [
            plan for row in locked_rows if (plan := _reset_boundary_recovery_plan(row)) is not None
        ]
        if recovery_plans:
            await _mark_reprocessing_jobs_failed(
                db,
                job_ids=[int(plan["id"]) for plan in recovery_plans],
                failure_reason=(
                    "invalid_reset_watermarks_job_payload: unsafe storage "
                    "representation; replay boundary recovered"
                ),
            )
    await db.execute(QUARANTINE_PENDING_RESET_UNSAFE_IDENTITIES)
    for plan in recovery_plans:
        await db.execute(UPSERT_PENDING_RESET_WATERMARKS, plan)
    await db.execute(QUARANTINE_PENDING_RESET_IDENTITY_COLLISIONS, parameters)
    result = await db.execute(NORMALIZE_PENDING_RESET_WATERMARKS, parameters)
    return int(result.scalar_one())


PENDING_FX_REPLAY_CANDIDATES = text(
    """
    SELECT
        id,
        payload::text AS payload_json,
        status,
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
      AND status IN ('PENDING', 'PROCESSING')
      AND CASE
          WHEN pg_input_is_valid(payload::text, 'jsonb') IS NOT TRUE THEN TRUE
          ELSE btrim(payload->>'from_currency', :trim_chars) = :from_currency
           AND btrim(payload->>'to_currency', :trim_chars) = :to_currency
      END
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
        payload::text AS payload_json,
        status,
        pg_input_is_valid(payload::text, 'jsonb') AS payload_representable,
        CASE
            WHEN pg_input_is_valid(payload::text, 'jsonb') IS NOT TRUE THEN FALSE
            WHEN json_typeof(payload->'earliest_impacted_date') IS DISTINCT FROM 'string'
            THEN FALSE
            ELSE pg_input_is_valid(payload->>'earliest_impacted_date', 'date')
        END AS earliest_date_representable
    FROM reprocessing_jobs
    WHERE job_type = 'RESET_WATERMARKS'
      AND status IN ('PENDING', 'PROCESSING')
      AND CASE
          WHEN pg_input_is_valid(payload::text, 'jsonb') IS NOT TRUE THEN TRUE
          ELSE btrim(payload->>'security_id', :trim_chars) = :security_id
      END
    """
).bindparams(
    bindparam("security_id", type_=String()),
    bindparam("trim_chars", type_=String()),
)

PENDING_RESET_REPLAY_SIBLING = text(
    """
    SELECT id, payload::text AS payload_json, status
    FROM reprocessing_jobs
    WHERE id <> :job_id
      AND job_type = 'RESET_WATERMARKS'
      AND status IN ('PENDING', 'PROCESSING')
      AND CASE
          WHEN pg_input_is_valid(payload::text, 'jsonb') IS NOT TRUE THEN TRUE
          ELSE btrim(payload->>'security_id', :trim_chars) = :security_id
      END
    ORDER BY id
    """
)

PENDING_FX_REPLAY_SIBLING = text(
    """
    SELECT
        id,
        payload::text AS payload_json,
        status
    FROM reprocessing_jobs
    WHERE id <> :job_id
      AND job_type = 'RESET_FX_WATERMARKS'
      AND status IN ('PENDING', 'PROCESSING')
      AND CASE
          WHEN pg_input_is_valid(payload::text, 'jsonb') IS NOT TRUE THEN TRUE
          ELSE btrim(payload->>'from_currency', :trim_chars) = :from_currency
           AND btrim(payload->>'to_currency', :trim_chars) = :to_currency
      END
    ORDER BY id
    """
)

LOCK_SCANNED_REPLAY_CANDIDATES = text(
    """
    SELECT
        id,
        payload::text AS payload_json,
        attempt_count,
        correlation_id,
        correlation_missing_reason,
        alternate_lookup_key,
        status,
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
    WHERE id = ANY(CAST(:candidate_ids AS BIGINT[]))
      AND job_type = :job_type
    ORDER BY id
    FOR UPDATE
    """
).bindparams(
    bindparam("candidate_ids"),
    bindparam("job_type", type_=String()),
)


async def _lock_scanned_replay_rows(
    db: AsyncSession,
    *,
    candidate_ids: list[int],
    job_type: str,
) -> list[Mapping[str, Any]]:
    if not candidate_ids:
        return []
    return (
        (
            await db.execute(
                LOCK_SCANNED_REPLAY_CANDIDATES,
                {"candidate_ids": sorted(set(candidate_ids)), "job_type": job_type},
            )
        )
        .mappings()
        .all()
    )


def replay_row_matches_identity(
    row: Mapping[str, Any],
    expected_identity: Mapping[str, str],
) -> bool:
    """Match the exact JSON identity text retained by PostgreSQL."""

    return all(
        (identity_text := _json_object_field_identity_text(row.get("payload_json"), field))
        is not None
        and identity_text.strip(REPLAY_TEXT_TRIM_CHARS) == expected
        for field, expected in expected_identity.items()
    )


async def _lock_matching_replay_rows(
    db: AsyncSession,
    *,
    scanned_rows: list[Mapping[str, Any]],
    job_type: str,
    expected_identity: Mapping[str, str],
) -> list[Mapping[str, Any]]:
    """Lock and revalidate only rows whose retained identity matches the request."""

    candidate_ids = sorted(
        {
            int(row["id"])
            for row in scanned_rows
            if replay_row_matches_identity(row, expected_identity)
        }
    )
    if not candidate_ids:
        return []
    locked_rows = await _lock_scanned_replay_rows(
        db,
        candidate_ids=candidate_ids,
        job_type=job_type,
    )
    return [row for row in locked_rows if replay_row_matches_identity(row, expected_identity)]


def _reset_boundary_recovery_plan(row: Mapping[str, Any]) -> dict[str, Any] | None:
    payload = _decode_retained_payload(row.get("payload_json"))
    if not isinstance(payload, dict):
        return None
    security_id = payload.get("security_id")
    earliest_value = payload.get("earliest_impacted_date")
    if not isinstance(security_id, str) or not isinstance(earliest_value, str):
        return None
    security_id = security_id.strip(REPLAY_TEXT_TRIM_CHARS)
    if not security_id or any(
        ord(character) <= 31 or 127 <= ord(character) <= 159 for character in security_id
    ):
        return None
    try:
        earliest_impacted_date = date.fromisoformat(earliest_value)
    except ValueError:
        return None
    return {
        "id": int(row["id"]),
        "identity_key": effective_dated_replay_identity_key("RESET_WATERMARKS", security_id),
        "security_id": security_id,
        "earliest_impacted_date": earliest_impacted_date,
        "attempt_count": int(row.get("attempt_count") or 0),
        "correlation_id": row.get("correlation_id"),
        "correlation_missing_reason": row.get("correlation_missing_reason"),
        "alternate_lookup_key": row.get("alternate_lookup_key"),
    }


def _json_object_field_identity_text(payload_json: object, field: str) -> str | None:
    """Extract a top-level JSON value without losing its stored lexical representation."""

    if not isinstance(payload_json, str):
        return None
    decoder = json.JSONDecoder(parse_int=Decimal, parse_float=Decimal)
    index = _skip_json_whitespace(payload_json, 0)
    if index >= len(payload_json) or payload_json[index] != "{":
        return None
    index += 1
    matched_value: str | None = None
    try:
        while True:
            index = _skip_json_whitespace(payload_json, index)
            if index >= len(payload_json) or payload_json[index] == "}":
                return matched_value
            key, index = decoder.raw_decode(payload_json, index)
            if not isinstance(key, str):
                return None
            index = _skip_json_whitespace(payload_json, index)
            if index >= len(payload_json) or payload_json[index] != ":":
                return None
            value_start = _skip_json_whitespace(payload_json, index + 1)
            _, value_end = decoder.raw_decode(payload_json, value_start)
            if key == field:
                matched_value = _postgres_json_identity_text(payload_json[value_start:value_end])
            index = _skip_json_whitespace(payload_json, value_end)
            if index >= len(payload_json):
                return None
            if payload_json[index] == "}":
                return matched_value
            if payload_json[index] != ",":
                return None
            index += 1
    except ValueError:
        return None


def _skip_json_whitespace(value: str, index: int) -> int:
    while index < len(value) and value[index] in " \t\r\n":
        index += 1
    return index


def _postgres_json_identity_text(encoded_value: object) -> str | None:
    """Convert raw JSON field text to the corresponding ``json ->>`` identity."""

    if not isinstance(encoded_value, str):
        return None
    try:
        decoded_value = json.loads(
            encoded_value,
            parse_int=Decimal,
            parse_float=Decimal,
        )
    except ValueError:
        return None
    if isinstance(decoded_value, str):
        return decoded_value
    if decoded_value is None:
        return None
    return encoded_value


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
    scanned_rows = (
        (
            await db.execute(
                statement,
                {"job_id": job_id, "trim_chars": REPLAY_TEXT_TRIM_CHARS, **expected_identity},
            )
        )
        .mappings()
        .all()
    )
    return bool(
        await _lock_matching_replay_rows(
            db,
            scanned_rows=scanned_rows,
            job_type=job_type,
            expected_identity=expected_identity,
        )
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
    expected_identity = {"from_currency": from_currency, "to_currency": to_currency}
    rows = await _lock_matching_replay_rows(
        db,
        scanned_rows=result.mappings().all(),
        job_type="RESET_FX_WATERMARKS",
        expected_identity=expected_identity,
    )
    return await _quarantine_candidates(
        db,
        rows=rows,
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
    expected_identity = {"security_id": security_id}
    rows = await _lock_matching_replay_rows(
        db,
        scanned_rows=result.mappings().all(),
        job_type="RESET_WATERMARKS",
        expected_identity=expected_identity,
    )
    return await _quarantine_candidates(
        db,
        rows=rows,
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
        payload = _decode_retained_payload(row.get("payload_json"))
        try:
            if not all(row[field] for field in required_validity_fields):
                raise ValueError("replay payload is not PostgreSQL-representable")
            validate(payload)
        except (TypeError, ValueError):
            if (earliest_date := parse_earliest_date(payload)) is not None:
                known_earliest_dates.append(earliest_date)
            if row["status"] == "PENDING":
                malformed_ids.append(int(row["id"]))

    await _mark_reprocessing_jobs_failed(
        db,
        job_ids=malformed_ids,
        failure_reason=failure_reason,
    )
    return min(known_earliest_dates, default=None)


async def _mark_reprocessing_jobs_failed(
    db: AsyncSession,
    *,
    job_ids: list[int],
    failure_reason: str,
) -> None:
    if not job_ids:
        return
    observe_multi_statement_batch(
        operation=StatementBatchOperation.REPROCESSING_INVALID_PAYLOAD_UPDATE,
        item_count=len(job_ids),
        binds_per_row=1,
        reserved_binds=2,
    )
    for job_id_chunk in iter_statement_chunks(
        job_ids,
        binds_per_row=1,
        reserved_binds=2,
    ):
        await db.execute(
            update(ReprocessingJob)
            .where(
                ReprocessingJob.id.in_(job_id_chunk),
                ReprocessingJob.status == "PENDING",
            )
            .values(
                status="FAILED",
                failure_reason=failure_reason,
                updated_at=func.now(),
            )
        )


def _decode_retained_payload(payload_json: object) -> object:
    """Decode retained JSON without Python's bounded integer conversion."""

    if not isinstance(payload_json, str):
        return None
    try:
        return json.loads(
            payload_json,
            parse_int=Decimal,
            parse_float=Decimal,
        )
    except (ValueError, RecursionError):
        return None
