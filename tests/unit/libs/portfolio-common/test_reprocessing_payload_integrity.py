"""Boundary tests for retained reprocessing payload quarantine."""

import json
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.reprocessing_payload_integrity import (
    PENDING_FX_REPLAY_CANDIDATES,
    PENDING_FX_REPLAY_SIBLING,
    PENDING_RESET_REPLAY_CANDIDATES,
    PENDING_RESET_REPLAY_SIBLING,
    _decode_retained_payload,
    _postgres_json_identity_text,
    _quarantine_candidates,
    pending_replay_sibling_exists,
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

    for statement in (PENDING_FX_REPLAY_SIBLING, PENDING_RESET_REPLAY_SIBLING):
        sql = str(statement)
        assert "payload::text AS payload_json" in sql
        assert "SELECT id, payload," not in sql
        assert "THEN TRUE" in sql
        assert "btrim(payload->>" in sql
        assert sql.index("WHEN pg_input_is_valid(payload::text, 'jsonb')") < sql.index(
            "btrim(payload->>"
        )


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
    payload = _decode_retained_payload(
        f'{{"security_id":"BOND-1","extension":{oversized_integer}}}'
    )

    assert isinstance(payload, dict)
    assert payload["security_id"] == "BOND-1"
    assert payload["extension"] == Decimal(oversized_integer)
    assert not replay_row_matches_identity(
        {"payload_json": '{"security_id":[ 123 ]}'},
        {"security_id": "[123]"},
    )


@pytest.mark.parametrize("payload_json", [None, '{"security_id":'])
def test_retained_payload_decode_fails_closed(payload_json: object) -> None:
    assert _decode_retained_payload(payload_json) is None


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
        {"payload_json": "{}"},
        {"payload_json": json.dumps(identity)},
    ]
    db.execute.return_value = result

    assert await pending_replay_sibling_exists(
        db,
        job_id=41,
        job_type=job_type,
        payload=payload,
    )
    executed_statement, parameters = db.execute.await_args.args
    assert executed_statement is statement
    assert parameters["job_id"] == 41
    assert all(parameters[field] == value for field, value in identity.items())


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
    result = MagicMock()
    result.mappings.return_value.all.return_value = [
        {"id": 7, "payload_json": json.dumps(retained), **validity},
        {
            "id": 8,
            "payload_json": '{"security_id":"OTHER"}',
            **validity,
        },
    ]
    db.execute.return_value = result

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
    assert db.execute.await_count == 2
    update_parameters = db.execute.await_args_list[1].args[0].compile().params
    assert next(value for value in update_parameters.values() if isinstance(value, list)) == [7]


@pytest.mark.asyncio
async def test_quarantine_leaves_valid_replay_work_unchanged() -> None:
    db = AsyncMock()

    earliest = await _quarantine_candidates(
        db,
        rows=[
            {
                "id": 9,
                "payload_json": '{"security_id":"BOND-1"}',
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
async def test_quarantine_updates_large_malformed_cohort_in_bounded_statements() -> None:
    db = AsyncMock()
    rows = [
        {
            "id": job_id,
            "payload_json": "{}",
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
