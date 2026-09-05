"""Boundary tests for retained reprocessing payload quarantine."""

import json
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.reprocessing_payload_integrity import (
    LOCK_SCANNED_REPLAY_CANDIDATES,
    NORMALIZE_PENDING_RESET_WATERMARKS,
    PENDING_FX_REPLAY_CANDIDATES,
    PENDING_FX_REPLAY_SIBLING,
    PENDING_RESET_REPLAY_CANDIDATES,
    PENDING_RESET_REPLAY_SIBLING,
    REPLAY_TEXT_TRIM_CHARS,
    _postgres_json_identity_text,
    _quarantine_candidates,
    _reset_boundary_recovery_plan,
    decode_reprocessing_payload_text,
    pending_replay_sibling_evidence,
    quarantine_pending_fx_pair,
    quarantine_pending_reset_security,
    replay_row_matches_identity,
)


def test_replay_identity_queries_guard_jsonb_invalid_rows_before_extraction() -> None:
    for statement in (PENDING_FX_REPLAY_CANDIDATES, PENDING_RESET_REPLAY_CANDIDATES):
        sql = str(statement)
        assert "payload::text AS payload_json" in sql
        assert "\n        payload," not in sql
        assert "AS payload_representable" in sql
        assert "THEN TRUE" in sql
        assert "btrim(payload->>" in sql
        assert sql.index("pg_input_is_valid(payload::text, 'jsonb')") < sql.index("json_typeof")
        guarded_predicate = sql.rindex("WHEN pg_input_is_valid(payload::text, 'jsonb')")
        assert guarded_predicate < sql.rindex("btrim(payload->>")
        assert "FOR UPDATE" not in sql
        assert "status IN ('PENDING', 'PROCESSING')" in sql

    for statement in (PENDING_FX_REPLAY_SIBLING, PENDING_RESET_REPLAY_SIBLING):
        sql = str(statement)
        assert "payload::text AS payload_json" in sql
        assert "SELECT id, payload," not in sql
        assert "THEN TRUE" in sql
        assert "btrim(payload->>" in sql
        assert sql.index("WHEN pg_input_is_valid(payload::text, 'jsonb')") < sql.index(
            "btrim(payload->>"
        )
        assert "FOR UPDATE" not in sql
        assert "status IN ('PENDING', 'PROCESSING')" in sql

    lock_sql = str(LOCK_SCANNED_REPLAY_CANDIDATES)
    assert "id = ANY(CAST(:candidate_ids AS BIGINT[]))" in lock_sql
    assert "status = 'PENDING'" in lock_sql
    assert "preserve_candidate_ids" in lock_sql
    assert "FOR UPDATE" in lock_sql
    assert lock_sql.index("pg_input_is_valid(payload::text, 'jsonb')") < lock_sql.index(
        "json_typeof"
    )


def test_reset_normalization_preserves_maximum_retry_history() -> None:
    sql = str(NORMALIZE_PENDING_RESET_WATERMARKS)
    assert "max(attempt_count) OVER (PARTITION BY security_id)" in sql
    assert "attempt_count = r.max_attempt_count" in sql
    assert "j.attempt_count <> r.max_attempt_count" in sql


def test_python_identity_match_distinguishes_unrelated_payload_poison() -> None:
    assert replay_row_matches_identity(
        {"payload_json": '{"security_id":" BOND-1 ","legacy_number":1e1000000}'},
        {"security_id": "BOND-1"},
    )
    assert not replay_row_matches_identity(
        {"payload_json": '{"security_id":"BOND\\u0000-1"}'},
        {"security_id": "BOND-1"},
    )


def test_python_identity_match_uses_postgres_json_text_semantics() -> None:
    assert replay_row_matches_identity(
        {"payload_json": '{"security_id":123}'}, {"security_id": "123"}
    )
    assert replay_row_matches_identity(
        {"payload_json": '{"security_id":true}'}, {"security_id": "true"}
    )
    assert replay_row_matches_identity(
        {"payload_json": '{"security_id":[123]}'}, {"security_id": "[123]"}
    )
    assert replay_row_matches_identity(
        {"payload_json": '{"security_id":{"scheme":"CUSIP"}}'},
        {"security_id": '{"scheme":"CUSIP"}'},
    )
    assert replay_row_matches_identity(
        {"payload_json": '{"security_id":1e2}'}, {"security_id": "1e2"}
    )
    assert not replay_row_matches_identity(
        {"payload_json": '{"security_id":null}'}, {"security_id": "null"}
    )


def test_python_identity_match_preserves_structured_whitespace_and_last_duplicate() -> None:
    assert replay_row_matches_identity(
        {"payload_json": '{"security_id":[ 123 ],"security_id":1e2}'},
        {"security_id": "1e2"},
    )


@pytest.mark.parametrize(
    "payload_json",
    [
        None,
        "[]",
        "{}",
        '{1:"BOND-1"}',
        '{"security_id" "BOND-1"}',
        '{"security_id":',
        '{"other":"value"',
        '{"other":"value";}',
    ],
)
def test_python_identity_match_fails_closed_for_malformed_or_missing_identity(
    payload_json: object,
) -> None:
    assert not replay_row_matches_identity(
        {"payload_json": payload_json},
        {"security_id": "BOND-1"},
    )


def test_postgres_identity_text_rejects_non_json_and_invalid_json() -> None:
    assert _postgres_json_identity_text(123) is None
    assert _postgres_json_identity_text("not-json") is None


def test_retained_payload_decode_preserves_oversized_numeric_type() -> None:
    oversized_integer = "1" * 5_000
    payload = decode_reprocessing_payload_text(
        f'{{"security_id":"BOND-1","extension":{oversized_integer}}}'
    )

    assert isinstance(payload, dict)
    assert payload["security_id"] == "BOND-1"
    assert payload["extension"] == Decimal(oversized_integer)
    assert not replay_row_matches_identity(
        {"payload_json": '{"security_id":[ 123 ]}'},
        {"security_id": "[123]"},
    )


def test_retained_identity_scan_ignores_unbounded_numeric_extension() -> None:
    unbounded_number = "1e" + ("9" * 40)
    payload_json = f'{{"security_id":"BOND-1","extension":{unbounded_number}}}'

    assert decode_reprocessing_payload_text(payload_json) is None
    assert replay_row_matches_identity(
        {"payload_json": payload_json},
        {"security_id": "BOND-1"},
    )
    assert _postgres_json_identity_text(unbounded_number) == unbounded_number


def test_reset_boundary_recovery_ignores_extensions_and_trims_boundary_controls() -> None:
    unbounded_number = "1e" + ("9" * 40)
    plan = _reset_boundary_recovery_plan(
        {
            "id": 8,
            "payload_json": (
                '{"security_id":"\\tRECOVERY-BOND\\t",'
                '"earliest_impacted_date":"2025-01-02",'
                f'"extension":{unbounded_number}}}'
            ),
        }
    )

    assert plan is not None
    assert plan["security_id"] == "RECOVERY-BOND"
    assert plan["earliest_impacted_date"] == date(2025, 1, 2)


def test_reset_boundary_recovery_plan_preserves_safe_identity_date_and_lineage() -> None:
    oversized_integer = "1" * 5_000
    plan = _reset_boundary_recovery_plan(
        {
            "id": 7,
            "payload_json": (
                '{"security_id":" RECOVERY-BOND ",'
                '"earliest_impacted_date":"2025-W01-2",'
                f'"extension":{oversized_integer}}}'
            ),
            "attempt_count": 3,
            "correlation_id": "corr-source",
            "correlation_missing_reason": None,
            "alternate_lookup_key": "alt-source",
        }
    )

    assert plan == {
        "id": 7,
        "identity_key": "RESET_WATERMARKS|13:RECOVERY-BOND",
        "security_id": "RECOVERY-BOND",
        "earliest_impacted_date": date(2024, 12, 31),
        "attempt_count": 3,
        "correlation_id": "corr-source",
        "correlation_missing_reason": None,
        "alternate_lookup_key": "alt-source",
    }


@pytest.mark.parametrize(
    "payload_json",
    [
        '{"security_id":123,"earliest_impacted_date":"2025-01-01"}',
        '{"security_id":"BAD\\u0000ID","earliest_impacted_date":"2025-01-01"}',
        '{"security_id":"BAD\\ud800ID","earliest_impacted_date":"2025-01-01"}',
        '{"security_id":"BOND-1","earliest_impacted_date":"2025-01-01 BC"}',
    ],
)
def test_reset_boundary_recovery_plan_rejects_unowned_or_unparseable_boundaries(
    payload_json: str,
) -> None:
    assert _reset_boundary_recovery_plan({"id": 7, "payload_json": payload_json}) is None


@pytest.mark.parametrize("payload_json", [None, '{"security_id":'])
def test_retained_payload_decode_fails_closed(payload_json: object) -> None:
    assert decode_reprocessing_payload_text(payload_json) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("job_type", "payload", "statement", "identity"),
    [
        (
            "RESET_WATERMARKS",
            {"security_id": "BOND-1"},
            PENDING_RESET_REPLAY_SIBLING,
            {"security_id": "BOND-1"},
        ),
        (
            "RESET_FX_WATERMARKS",
            {"from_currency": "USD", "to_currency": "CHF"},
            PENDING_FX_REPLAY_SIBLING,
            {"from_currency": "USD", "to_currency": "CHF"},
        ),
    ],
)
async def test_pending_sibling_requires_exact_retained_identity(
    job_type: str,
    payload: dict[str, str],
    statement: object,
    identity: dict[str, str],
) -> None:
    db = AsyncMock()
    result = MagicMock()
    result.mappings.return_value.all.return_value = [
        {"id": 7, "payload_json": "{}", "status": "PENDING"},
        {
            "id": 8,
            "payload_json": json.dumps({**identity, "earliest_impacted_date": "2025-01-03"}),
            "status": "PROCESSING",
        },
    ]
    db.execute.return_value = result

    evidence = await pending_replay_sibling_evidence(
        db,
        job_id=41,
        job_type=job_type,
        payload=payload,
    )
    assert evidence.exists is True
    assert evidence.earliest_sibling.earliest_impacted_date == date(2025, 1, 3)
    scanned_statement, scanned_parameters = db.execute.await_args_list[0].args
    assert scanned_statement is statement
    assert scanned_parameters["job_id"] == 41
    assert all(scanned_parameters[field] == value for field, value in identity.items())
    locked_statement, locked_parameters = db.execute.await_args_list[1].args
    assert locked_statement is LOCK_SCANNED_REPLAY_CANDIDATES
    assert locked_parameters == {
        "candidate_ids": [8],
        "preserve_candidate_ids": [8],
        "job_type": job_type,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("quarantine", "identity", "candidate_statement"),
    [
        (
            quarantine_pending_reset_security,
            {"security_id": "BOND-1"},
            PENDING_RESET_REPLAY_CANDIDATES,
        ),
        (
            quarantine_pending_fx_pair,
            {"from_currency": "USD", "to_currency": "CHF"},
            PENDING_FX_REPLAY_CANDIDATES,
        ),
    ],
)
async def test_quarantine_preserves_only_matching_malformed_replay_boundary(
    quarantine,
    identity: dict[str, str],
    candidate_statement: object,
) -> None:
    db = AsyncMock()
    retained = {**identity, "earliest_date": "2026-09-01"}
    validity = {
        "payload_representable": False,
        "earliest_date_representable": True,
        "generated_at_representable": True,
    }
    scan_result = MagicMock()
    scan_result.mappings.return_value.all.return_value = [
        {"id": 7, "payload_json": json.dumps(retained), "status": "PENDING", **validity},
        {
            "id": 8,
            "payload_json": '{"security_id":"OTHER"}',
            "status": "PENDING",
            **validity,
        },
    ]
    lock_result = MagicMock()
    lock_result.mappings.return_value.all.return_value = [
        {"id": 7, "payload_json": json.dumps(retained), "status": "PENDING", **validity}
    ]
    update_result = MagicMock()
    db.execute.side_effect = [scan_result, lock_result, update_result]

    earliest = await quarantine(
        db,
        **identity,
        validate=lambda payload: payload,
        parse_earliest_date=lambda payload: (
            date.fromisoformat(payload["earliest_date"])
            if isinstance(payload, dict) and payload.get("earliest_date")
            else None
        ),
    )

    assert earliest == date(2026, 9, 1)
    assert db.execute.await_args_list[0].args[0] is candidate_statement
    locked_statement, locked_parameters = db.execute.await_args_list[1].args
    assert locked_statement is LOCK_SCANNED_REPLAY_CANDIDATES
    assert locked_parameters["candidate_ids"] == [7]
    assert locked_parameters["preserve_candidate_ids"] == [7]
    assert db.execute.await_count == 3
    update_parameters = db.execute.await_args_list[2].args[0].compile().params
    assert next(value for value in update_parameters.values() if isinstance(value, list)) == [7]


@pytest.mark.asyncio
async def test_fx_quarantine_recovers_date_before_unbounded_numeric_extension() -> None:
    unbounded_number = "1e" + ("9" * 40)
    retained = (
        '{"from_currency":"USD","to_currency":"CHF",'
        '"earliest_impacted_date":"2026-09-01",'
        f'"extension":{unbounded_number}}}'
    )
    row = {
        "id": 7,
        "payload_json": retained,
        "status": "PENDING",
        "payload_representable": False,
        "earliest_date_representable": False,
        "generated_at_representable": False,
    }
    db = AsyncMock()
    scan_result = MagicMock()
    scan_result.mappings.return_value.all.return_value = [row]
    lock_result = MagicMock()
    lock_result.mappings.return_value.all.return_value = [row]
    db.execute.side_effect = [scan_result, lock_result, MagicMock()]

    earliest = await quarantine_pending_fx_pair(
        db,
        from_currency="USD",
        to_currency="CHF",
        validate=lambda payload: payload,
        parse_earliest_date=lambda payload: None,
    )

    assert earliest == date(2026, 9, 1)


@pytest.mark.asyncio
async def test_quarantine_does_not_row_lock_valid_processing_work() -> None:
    db = AsyncMock()
    scan_result = MagicMock()
    scan_result.mappings.return_value.all.return_value = [
        {
            "id": 7,
            "payload_json": ('{"security_id":"BOND-1","earliest_impacted_date":"2025-01-03"}'),
            "status": "PROCESSING",
            "payload_representable": True,
            "earliest_date_representable": True,
        }
    ]
    db.execute.return_value = scan_result

    earliest = await quarantine_pending_reset_security(
        db,
        security_id="BOND-1",
        validate=lambda payload: payload,
        parse_earliest_date=lambda payload: (
            date.fromisoformat(payload["earliest_impacted_date"])
            if isinstance(payload, dict)
            else None
        ),
    )

    assert earliest is None
    db.execute.assert_awaited_once_with(
        PENDING_RESET_REPLAY_CANDIDATES,
        {"security_id": "BOND-1", "trim_chars": REPLAY_TEXT_TRIM_CHARS},
    )


@pytest.mark.asyncio
async def test_quarantine_leaves_valid_replay_work_unchanged() -> None:
    db = AsyncMock()

    earliest = await _quarantine_candidates(
        db,
        rows=[
            {
                "id": 9,
                "payload_json": '{"security_id":"BOND-1"}',
                "status": "PENDING",
                "payload_representable": True,
                "earliest_date_representable": True,
            }
        ],
        required_validity_fields=("payload_representable", "earliest_date_representable"),
        validate=lambda payload: payload,
        parse_earliest_date=lambda payload: None,
        failure_reason="invalid retained replay",
    )

    assert earliest is None
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_quarantine_preserves_processing_boundary_without_stealing_lease() -> None:
    db = AsyncMock()

    earliest = await _quarantine_candidates(
        db,
        rows=[
            {
                "id": 9,
                "payload_json": (
                    '{"security_id":"BOND-1","earliest_impacted_date":"2025-01-03",'
                    '"extension":1e1000000}'
                ),
                "status": "PROCESSING",
                "payload_representable": False,
                "earliest_date_representable": False,
            }
        ],
        required_validity_fields=("payload_representable", "earliest_date_representable"),
        validate=lambda payload: payload,
        parse_earliest_date=lambda payload: (
            date.fromisoformat(payload["earliest_impacted_date"])
            if isinstance(payload, dict)
            else None
        ),
        failure_reason="invalid retained replay",
    )

    assert earliest == date(2025, 1, 3)
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_quarantine_updates_large_malformed_cohort_in_bounded_statements() -> None:
    db = AsyncMock()
    rows = [
        {
            "id": job_id,
            "payload_json": "{}",
            "status": "PENDING",
            "payload_representable": False,
            "earliest_date_representable": False,
        }
        for job_id in range(1, 1_002)
    ]

    earliest = await _quarantine_candidates(
        db,
        rows=rows,
        required_validity_fields=("payload_representable", "earliest_date_representable"),
        validate=lambda payload: payload,
        parse_earliest_date=lambda payload: None,
        failure_reason="invalid retained replay",
    )

    assert earliest is None
    assert db.execute.await_count == 2
    chunk_sizes = []
    for call in db.execute.await_args_list:
        parameters = call.args[0].compile().params
        chunk_sizes.append(
            len(next(value for value in parameters.values() if isinstance(value, list)))
        )
    assert chunk_sizes == [1_000, 1]
