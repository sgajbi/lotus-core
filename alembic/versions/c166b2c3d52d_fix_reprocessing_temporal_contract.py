"""Align active reprocessing temporal values with PostgreSQL representation.

Revision ID: c166b2c3d52d
Revises: c165b2c3d52c
Create Date: 2026-09-05
"""

import unicodedata
from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "c166b2c3d52d"
down_revision: str | Sequence[str] | None = "c165b2c3d52c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE_NAME = "reprocessing_jobs"
_ACTIVE_PAYLOAD_CONSTRAINT = "ck_reprocessing_jobs_active_payload_valid"
_CUTOVER_FAILURE_REASON = "invalid_reprocessing_job_payload: quarantined during contract cutover"
_RECOVERED_FAILURE_REASON = (
    "invalid_reprocessing_job_payload: recovered by c166 temporal-contract correction"
)
_PYTHON_ISO_DATE_PATTERN = (
    r"'^(?:[0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{8}|"
    r"[0-9]{4}-W[0-9]{2}(?:-[1-7])?|[0-9]{4}W[0-9]{2}[1-7]?)$'"
)
_PYTHON_ISO_DATE_TEXT_VALID = (
    "pg_input_is_valid(payload->>'earliest_impacted_date', 'date') IS TRUE "
    f"AND payload->>'earliest_impacted_date' ~ {_PYTHON_ISO_DATE_PATTERN}"
)
_REPLAY_TEXT_TRIM_CHARS = (
    r"U&' \0009\000A\000B\000C\000D\001C\001D\001E\001F\0020\0085\00A0\1680"
    r"\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A\2028\2029"
    r"\202F\205F\3000'"
)
_REPLAY_CONTROL_PATTERN = r"U&'[\0001-\001F\007F-\009F]'"
_OLD_FX_GENERATED_AT_TIMEZONE_PATTERN = (
    r"'^[0-9]{4}-?[0-9]{2}-?[0-9]{2}.+[0-9]{2}"
    r".*(Z|[+-][0-9]{2}:?[0-9]{2}(:?[0-9]{2}([.,][0-9]+)?)?)$'"
)
_FX_GENERATED_AT_TIMEZONE_PATTERN = (
    r"'^[0-9]{4}-?[0-9]{2}-?[0-9]{2}[T ]"
    r"(([01][0-9]|2[0-3]):[0-5][0-9](:[0-5][0-9]([.,][0-9]+)?)?|"
    r"([01][0-9]|2[0-3])[0-5][0-9]([0-5][0-9]([.,][0-9]+)?)?)"
    r"(Z|[+-]([0-9]{2}|[0-9]{2}:[0-5][0-9](:[0-5][0-9]([.,][0-9]+)?)?|"
    r"[0-9]{2}[0-5][0-9]([0-5][0-9]([.,][0-9]+)?)?))$'"
)


def _normalized_replay_text_sql(expression: str) -> str:
    return (
        f"nullif({expression}, '') IS NOT NULL "
        f"AND {expression} = btrim({expression}, {_REPLAY_TEXT_TRIM_CHARS}) "
        f"AND {expression} !~ {_REPLAY_CONTROL_PATTERN}"
    )


_FX_FROM_CURRENCY_TEXT_VALID = _normalized_replay_text_sql("payload->>'from_currency'")
_FX_TO_CURRENCY_TEXT_VALID = _normalized_replay_text_sql("payload->>'to_currency'")
_FX_CONTENT_HASH_TEXT_VALID = _normalized_replay_text_sql("payload->>'content_hash'")
_FX_EARLIEST_DATE_TEXT_VALID = _normalized_replay_text_sql("payload->>'earliest_impacted_date'")
_FX_GENERATED_AT_TEXT_VALID = _normalized_replay_text_sql("payload->>'generated_at'")
_RESET_SECURITY_ID_TEXT_VALID = _normalized_replay_text_sql("payload->>'security_id'")


def _active_payload_constraint(
    timezone_pattern: str,
    *,
    require_python_date_grammar: bool = True,
) -> str:
    python_date_clause = (
        f"AND ({_PYTHON_ISO_DATE_TEXT_VALID})"
        if require_python_date_grammar
        else "AND pg_input_is_valid(payload->>'earliest_impacted_date', 'date') IS TRUE"
    )
    return f"""
        CASE
            WHEN status NOT IN ('PENDING', 'PROCESSING') THEN TRUE
            WHEN job_type NOT IN ('RESET_FX_WATERMARKS', 'RESET_WATERMARKS') THEN TRUE
            WHEN pg_input_is_valid(payload::text, 'jsonb') IS NOT TRUE THEN FALSE
            WHEN job_type = 'RESET_FX_WATERMARKS' THEN (
                jsonb_typeof(payload::jsonb->'from_currency') IS NOT DISTINCT FROM 'string'
                AND jsonb_typeof(payload::jsonb->'to_currency') IS NOT DISTINCT FROM 'string'
                AND jsonb_typeof(payload::jsonb->'content_hash') IS NOT DISTINCT FROM 'string'
                AND jsonb_typeof(payload::jsonb->'earliest_impacted_date')
                    IS NOT DISTINCT FROM 'string'
                AND jsonb_typeof(payload::jsonb->'generated_at') IS NOT DISTINCT FROM 'string'
                AND ({_FX_FROM_CURRENCY_TEXT_VALID})
                AND ({_FX_TO_CURRENCY_TEXT_VALID})
                AND ({_FX_CONTENT_HASH_TEXT_VALID})
                AND ({_FX_EARLIEST_DATE_TEXT_VALID})
                AND ({_FX_GENERATED_AT_TEXT_VALID})
                {python_date_clause}
                AND pg_input_is_valid(
                    payload->>'generated_at', 'timestamp with time zone'
                ) IS TRUE
                AND payload->>'generated_at' ~ {timezone_pattern}
            )
            WHEN job_type = 'RESET_WATERMARKS' THEN (
                jsonb_typeof(payload::jsonb->'security_id') IS NOT DISTINCT FROM 'string'
                AND jsonb_typeof(payload::jsonb->'earliest_impacted_date')
                    IS NOT DISTINCT FROM 'string'
                AND ({_RESET_SECURITY_ID_TEXT_VALID})
                AND ({_FX_EARLIEST_DATE_TEXT_VALID})
                {python_date_clause}
            )
            ELSE TRUE
        END
    """


_CUTOVER_GUARD = sa.text(
    """
    DO $$
    BEGIN
        PERFORM set_config('lock_timeout', '5s', true);
        LOCK TABLE reprocessing_jobs IN ACCESS EXCLUSIVE MODE;

        IF EXISTS (
            SELECT 1 FROM reprocessing_jobs WHERE status = 'PROCESSING'
        ) THEN
            RAISE EXCEPTION USING
                MESSAGE = 'temporal cutover requires a drained PROCESSING queue',
                HINT = 'pause the worker, recover or terminalize in-flight rows, then retry';
        END IF;
    END
    $$
    """
)
_RECOVERY_CANDIDATES = sa.text(
    rf"""
    SELECT
        id,
        payload,
        attempt_count,
        correlation_id,
        correlation_missing_reason,
        alternate_lookup_key,
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
        END AS generated_at_representable,
        CASE
            WHEN pg_input_is_valid(payload::text, 'jsonb') IS NOT TRUE THEN FALSE
            WHEN json_typeof(payload->'generated_at') IS DISTINCT FROM 'string'
            THEN FALSE
            ELSE payload->>'generated_at' ~ {_FX_GENERATED_AT_TIMEZONE_PATTERN}
        END AS timezone_pattern_matches
    FROM reprocessing_jobs
    WHERE job_type = 'RESET_FX_WATERMARKS'
      AND status = 'FAILED'
      AND failure_reason = :failure_reason
    ORDER BY id
    """
)
_QUARANTINE_PYTHON_INVALID_PENDING_TEMPORAL_VALUES = sa.text(
    rf"""
    UPDATE reprocessing_jobs
    SET status = 'FAILED',
        failure_reason = (
            'invalid_reprocessing_job_payload: quarantined by c166 temporal grammar correction'
        ),
        updated_at = now()
    WHERE status = 'PENDING'
      AND job_type IN ('RESET_FX_WATERMARKS', 'RESET_WATERMARKS')
      AND pg_input_is_valid(payload::text, 'jsonb') IS TRUE
      AND (
          (
              json_typeof(payload->'earliest_impacted_date') = 'string'
              AND pg_input_is_valid(payload->>'earliest_impacted_date', 'date') IS TRUE
              AND payload->>'earliest_impacted_date' !~ {_PYTHON_ISO_DATE_PATTERN}
          )
          OR (
              job_type = 'RESET_FX_WATERMARKS'
              AND json_typeof(payload->'generated_at') = 'string'
              AND pg_input_is_valid(
                  payload->>'generated_at', 'timestamp with time zone'
              ) IS TRUE
              AND payload->>'generated_at' !~ {_FX_GENERATED_AT_TIMEZONE_PATTERN}
          )
      )
    """
)
_RESTAGE_RECOVERABLE_FX = sa.text(
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
        'RESET_FX_WATERMARKS',
        json_build_object(
            'from_currency', :from_currency,
            'to_currency', :to_currency,
            'earliest_impacted_date', CAST(:earliest_impacted_date AS date)::text,
            'content_hash', :content_hash,
            'generated_at', :generated_at_text
        )::json,
        'PENDING',
        :attempt_count,
        :correlation_id,
        :correlation_missing_reason,
        :alternate_lookup_key
    )
    ON CONFLICT ((payload->>'from_currency'), (payload->>'to_currency'))
    WHERE job_type = 'RESET_FX_WATERMARKS' AND status = 'PENDING'
    DO UPDATE SET
        payload = json_build_object(
            'from_currency', :from_currency,
            'to_currency', :to_currency,
            'earliest_impacted_date', LEAST(
                (reprocessing_jobs.payload->>'earliest_impacted_date')::date,
                CAST(:earliest_impacted_date AS date)
            )::text,
            'content_hash', CASE
                WHEN ROW(CAST(:generated_at AS timestamptz), :content_hash) > ROW(
                    CAST(reprocessing_jobs.payload->>'generated_at' AS timestamptz),
                    reprocessing_jobs.payload->>'content_hash'
                )
                THEN :content_hash
                ELSE reprocessing_jobs.payload->>'content_hash'
            END,
            'generated_at', CASE
                WHEN ROW(CAST(:generated_at AS timestamptz), :content_hash) > ROW(
                    CAST(reprocessing_jobs.payload->>'generated_at' AS timestamptz),
                    reprocessing_jobs.payload->>'content_hash'
                )
                THEN :generated_at_text
                ELSE reprocessing_jobs.payload->>'generated_at'
            END
        )::json,
        attempt_count = GREATEST(reprocessing_jobs.attempt_count, EXCLUDED.attempt_count),
        correlation_id = CASE
            WHEN ROW(CAST(:generated_at AS timestamptz), :content_hash) > ROW(
                CAST(reprocessing_jobs.payload->>'generated_at' AS timestamptz),
                reprocessing_jobs.payload->>'content_hash'
            )
            THEN COALESCE(:correlation_id, reprocessing_jobs.correlation_id)
            ELSE reprocessing_jobs.correlation_id
        END,
        correlation_missing_reason = CASE
            WHEN ROW(CAST(:generated_at AS timestamptz), :content_hash) <= ROW(
                CAST(reprocessing_jobs.payload->>'generated_at' AS timestamptz),
                reprocessing_jobs.payload->>'content_hash'
            ) THEN reprocessing_jobs.correlation_missing_reason
            WHEN :correlation_id IS NOT NULL THEN NULL
            ELSE reprocessing_jobs.correlation_missing_reason
        END,
        alternate_lookup_key = CASE
            WHEN ROW(CAST(:generated_at AS timestamptz), :content_hash) <= ROW(
                CAST(reprocessing_jobs.payload->>'generated_at' AS timestamptz),
                reprocessing_jobs.payload->>'content_hash'
            ) THEN reprocessing_jobs.alternate_lookup_key
            WHEN :correlation_id IS NOT NULL THEN NULL
            ELSE reprocessing_jobs.alternate_lookup_key
        END,
        updated_at = now()
    """
).bindparams(
    sa.bindparam("earliest_impacted_date", type_=sa.Date()),
    sa.bindparam("generated_at", type_=sa.DateTime(timezone=True)),
)
_MARK_RECOVERED_SOURCE = sa.text(
    """
    UPDATE reprocessing_jobs
    SET failure_reason = :recovered_failure_reason,
        updated_at = now()
    WHERE id = :source_job_id
      AND status = 'FAILED'
      AND failure_reason = :cutover_failure_reason
    """
)
_DOWNGRADE_PREFLIGHT = sa.text(
    rf"""
    DO $$
    DECLARE
        incompatible_count bigint;
    BEGIN
        PERFORM set_config('lock_timeout', '5s', true);
        LOCK TABLE reprocessing_jobs IN ACCESS EXCLUSIVE MODE;
        SELECT count(*)
        INTO incompatible_count
        FROM reprocessing_jobs
        WHERE status IN ('PENDING', 'PROCESSING')
          AND job_type = 'RESET_FX_WATERMARKS'
          AND payload->>'generated_at' ~ {_FX_GENERATED_AT_TIMEZONE_PATTERN}
          AND payload->>'generated_at' !~ {_OLD_FX_GENERATED_AT_TIMEZONE_PATTERN};

        IF incompatible_count > 0 THEN
            RAISE EXCEPTION USING
                MESSAGE = format(
                    'reprocessing temporal-contract downgrade found % active row(s) '
                    'unsupported by the predecessor constraint',
                    incompatible_count
                ),
                HINT = (
                    'drain or terminalize the affected replay work without rewriting source '
                    'payload evidence, then retry the downgrade'
                );
        END IF;
    END
    $$
    """
)


def upgrade() -> None:
    """Install the parser/database intersection and recover provably valid work."""

    op.execute(_CUTOVER_GUARD)
    bind = op.get_bind()
    candidates = list(
        bind.execute(
            _RECOVERY_CANDIDATES,
            {"failure_reason": _CUTOVER_FAILURE_REASON},
        ).mappings()
    )
    recoverable = [
        recovered
        for row in candidates
        if (recovered := _recoverable_fx_parameters(row)) is not None
    ]
    bind.execute(_QUARANTINE_PYTHON_INVALID_PENDING_TEMPORAL_VALUES)

    op.drop_constraint(_ACTIVE_PAYLOAD_CONSTRAINT, _TABLE_NAME, type_="check")
    op.create_check_constraint(
        _ACTIVE_PAYLOAD_CONSTRAINT,
        _TABLE_NAME,
        _active_payload_constraint(_FX_GENERATED_AT_TIMEZONE_PATTERN),
    )
    if recoverable:
        ordered_recoverable = sorted(
            recoverable,
            key=lambda item: (
                item["from_currency"],
                item["to_currency"],
                item["generated_at"],
                item["content_hash"],
                item["source_job_id"],
            ),
        )
        bind.execute(
            _RESTAGE_RECOVERABLE_FX,
            ordered_recoverable,
        )
        bind.execute(
            _MARK_RECOVERED_SOURCE,
            [
                {
                    "source_job_id": item["source_job_id"],
                    "cutover_failure_reason": _CUTOVER_FAILURE_REASON,
                    "recovered_failure_reason": _RECOVERED_FAILURE_REASON,
                }
                for item in ordered_recoverable
            ],
        )


def _recoverable_fx_parameters(row: Any) -> dict[str, Any] | None:
    if not row["payload_representable"]:
        return None
    payload = row["payload"]
    if not isinstance(payload, dict):
        return None
    try:
        from_currency = _required_text(payload, "from_currency")
        to_currency = _required_text(payload, "to_currency")
        content_hash = _required_text(payload, "content_hash")
        earliest_date_text = _required_text(payload, "earliest_impacted_date")
        generated_at_text = _required_text(payload, "generated_at")
        earliest_impacted_date = date.fromisoformat(earliest_date_text)
        generated_at = datetime.fromisoformat(generated_at_text)
        if generated_at.tzinfo is None or generated_at.utcoffset() is None:
            return None
        if not row["earliest_date_representable"]:
            return None
        if not row["generated_at_representable"]:
            return None
        if not row["timezone_pattern_matches"]:
            return None
    except (TypeError, ValueError):
        return None
    return {
        "source_job_id": int(row["id"]),
        "from_currency": from_currency,
        "to_currency": to_currency,
        "earliest_impacted_date": earliest_impacted_date,
        "content_hash": content_hash,
        "generated_at": generated_at,
        "generated_at_text": generated_at_text,
        "attempt_count": int(row["attempt_count"]),
        "correlation_id": row["correlation_id"],
        "correlation_missing_reason": row["correlation_missing_reason"],
        "alternate_lookup_key": row["alternate_lookup_key"],
    }


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"reprocessing payload requires normalized {key}")
    if any(unicodedata.category(character) == "Cc" for character in value):
        raise ValueError(f"reprocessing payload {key} contains a control character")
    return value


def downgrade() -> None:
    """Restore the predecessor constraint only when no active evidence would be lost."""

    op.execute(_DOWNGRADE_PREFLIGHT)
    op.drop_constraint(_ACTIVE_PAYLOAD_CONSTRAINT, _TABLE_NAME, type_="check")
    op.create_check_constraint(
        _ACTIVE_PAYLOAD_CONSTRAINT,
        _TABLE_NAME,
        _active_payload_constraint(
            _OLD_FX_GENERATED_AT_TIMEZONE_PATTERN,
            require_python_date_grammar=False,
        ),
    )
