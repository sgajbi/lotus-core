"""Boundary tests for retained reprocessing payload quarantine."""

from unittest.mock import AsyncMock

import pytest
from portfolio_common.reprocessing_payload_integrity import (
    PENDING_FX_REPLAY_CANDIDATES,
    PENDING_FX_REPLAY_SIBLING,
    PENDING_RESET_REPLAY_CANDIDATES,
    PENDING_RESET_REPLAY_SIBLING,
    _quarantine_candidates,
    replay_row_matches_identity,
)


def test_replay_identity_queries_guard_jsonb_invalid_rows_before_extraction() -> None:
    for statement in (PENDING_FX_REPLAY_CANDIDATES, PENDING_RESET_REPLAY_CANDIDATES):
        sql = str(statement)
        assert "payload::text AS payload_json" in sql
        assert "AS payload_representable" in sql
        assert "THEN TRUE" in sql
        assert "btrim(payload->>" in sql
        assert sql.index("pg_input_is_valid(payload::text, 'jsonb')") < sql.index("json_typeof")
        guarded_predicate = sql.rindex("WHEN pg_input_is_valid(payload::text, 'jsonb')")
        assert guarded_predicate < sql.rindex("btrim(payload->>")

    for statement in (PENDING_FX_REPLAY_SIBLING, PENDING_RESET_REPLAY_SIBLING):
        sql = str(statement)
        assert "payload::text AS payload_json" in sql
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
    assert not replay_row_matches_identity(
        {"payload_json": '{"security_id":[ 123 ]}'},
        {"security_id": "[123]"},
    )


@pytest.mark.asyncio
async def test_quarantine_updates_large_malformed_cohort_in_bounded_statements() -> None:
    db = AsyncMock()
    rows = [
        {
            "id": job_id,
            "payload": {},
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
