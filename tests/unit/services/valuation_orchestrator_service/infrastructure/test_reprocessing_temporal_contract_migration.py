"""Contract proof for forward-only reprocessing temporal compatibility."""

from __future__ import annotations

import json
import runpy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

from portfolio_common.database_models import ReprocessingJob

from alembic import op

MIGRATION = (
    Path(__file__).resolve().parents[5]
    / "alembic"
    / "versions"
    / "c166b2c3d52d_fix_reprocessing_temporal_contract.py"
)


def _normalized_sql(value: object) -> str:
    return " ".join(str(value).split())


def _recoverable_row(**overrides: object) -> dict[str, object]:
    payload = overrides.pop(
        "payload",
        {
            "from_currency": "USD",
            "to_currency": "SGD",
            "earliest_impacted_date": "2025-01-04",
            "content_hash": "sha256:" + ("a" * 64),
            "generated_at": "2025-01-07T08:00:00-07",
        },
    )
    row: dict[str, object] = {
        "id": 17,
        "payload_json": json.dumps(payload),
        "attempt_count": 2,
        "correlation_id": "corr-recovered",
        "correlation_missing_reason": None,
        "alternate_lookup_key": None,
        "payload_representable": True,
        "earliest_date_representable": True,
        "generated_at_representable": True,
        "timezone_pattern_matches": True,
    }
    row.update(overrides)
    return row


def test_upgrade_replaces_constraint_and_restages_only_provable_work(monkeypatch) -> None:
    operations: list[tuple[object, ...]] = []
    bind = MagicMock()
    candidate_result = MagicMock()
    candidate_result.mappings.return_value = [
        _recoverable_row(),
        _recoverable_row(
            id=18,
            generated_at_representable=False,
        ),
    ]
    quarantine_result = MagicMock()
    quarantine_result.one.return_value = MagicMock(reset_count=3, reset_fx_count=5)
    bind.execute.side_effect = [candidate_result, quarantine_result, MagicMock(), MagicMock()]
    monkeypatch.setattr(op, "execute", lambda statement: operations.append(("execute", statement)))
    monkeypatch.setattr(op, "get_bind", lambda: bind)
    monkeypatch.setattr(
        op,
        "drop_constraint",
        lambda name, table, **kwargs: operations.append(("drop", name, table, kwargs)),
    )
    monkeypatch.setattr(
        op,
        "create_check_constraint",
        lambda name, table, condition: operations.append(("create", name, table, condition)),
    )

    migration = runpy.run_path(str(MIGRATION))
    assert migration["logger"].name == "alembic.runtime.migration"
    migration_logger = MagicMock()
    migration["upgrade"].__globals__["logger"] = migration_logger
    assert migration["revision"] == "c166b2c3d52d"
    assert migration["down_revision"] == "c165b2c3d52c"

    migration["upgrade"]()

    cutover_guard = str(operations[0][1])
    assert "set_config('lock_timeout', '5s', true)" in cutover_guard
    assert "ACCESS EXCLUSIVE" in cutover_guard
    assert cutover_guard.index("set_config") < cutover_guard.index("LOCK TABLE")
    assert "status = 'PROCESSING'" in cutover_guard
    assert "requires a drained PROCESSING queue" in cutover_guard
    assert cutover_guard.index("LOCK TABLE") < cutover_guard.index("status = 'PROCESSING'")
    assert "invalid_active_payload_count" in cutover_guard
    assert "status = 'PENDING'" in cutover_guard
    assert "job_type IN ('RESET_FX_WATERMARKS', 'RESET_WATERMARKS')" in cutover_guard
    assert "pg_input_is_valid(payload::text, 'jsonb') IS NOT TRUE" in cutover_guard
    assert "pending row(s) whose payload" in cutover_guard
    assert "cannot be represented as jsonb" in cutover_guard
    assert "without rewriting source" in cutover_guard
    assert "payload evidence, then retry the migration" in cutover_guard
    assert cutover_guard.index("requires a drained PROCESSING queue") < cutover_guard.index(
        "invalid_active_payload_count > 0"
    )
    assert operations[1][:3] == (
        "drop",
        "ck_reprocessing_jobs_active_payload_valid",
        "reprocessing_jobs",
    )
    assert operations[2][:3] == (
        "create",
        "ck_reprocessing_jobs_active_payload_valid",
        "reprocessing_jobs",
    )
    corrected_constraint = operations[2][3]
    assert "[T ]" in corrected_constraint
    assert "([01][0-9]|2[0-3])" in corrected_constraint
    assert ".+" not in corrected_constraint
    model_constraint = next(
        item
        for item in ReprocessingJob.__table__.constraints
        if item.name == "ck_reprocessing_jobs_active_payload_valid"
    )
    assert _normalized_sql(corrected_constraint) == _normalized_sql(model_constraint.sqltext)

    recovery_query, query_parameters = bind.execute.call_args_list[0].args
    assert "status = 'FAILED'" in str(recovery_query)
    assert "pg_input_is_valid" in str(recovery_query)
    recovery_sql = str(recovery_query)
    assert "payload::text AS payload_json" in recovery_sql
    assert "\n        payload," not in recovery_sql
    assert recovery_sql.count("pg_input_is_valid(payload::text, 'jsonb')") == 4
    assert recovery_sql.index("pg_input_is_valid(payload::text, 'jsonb')") < recovery_sql.index(
        "json_typeof"
    )
    assert query_parameters == {
        "failure_reason": ("invalid_reprocessing_job_payload: quarantined during contract cutover")
    }
    quarantine_statement = bind.execute.call_args_list[1].args[0]
    assert "c166 temporal grammar correction" in str(quarantine_statement)
    assert "earliest_impacted_date' !~" in str(quarantine_statement)
    assert "generated_at' !~" in str(quarantine_statement)
    assert "RETURNING job_type" in str(quarantine_statement)
    assert "count(*) FILTER (WHERE job_type = 'RESET_WATERMARKS')" in str(quarantine_statement)
    assert "count(*) FILTER (WHERE job_type = 'RESET_FX_WATERMARKS')" in str(quarantine_statement)
    quarantine_result.one.assert_called_once_with()
    migration_logger.info.assert_called_once_with(
        "reprocessing temporal grammar correction quarantined rows: "
        "reset_watermarks_count=%d reset_fx_watermarks_count=%d",
        3,
        5,
        extra={"reset_watermarks_count": 3, "reset_fx_watermarks_count": 5},
    )
    recovery_statement, recovery_parameters = bind.execute.call_args_list[2].args
    assert "ON CONFLICT" in str(recovery_statement)
    assert len(recovery_parameters) == 1
    assert recovery_parameters[0]["source_job_id"] == 17
    assert recovery_parameters[0]["earliest_impacted_date"] == date(2025, 1, 4)
    assert recovery_parameters[0]["generated_at"] == datetime(
        2025,
        1,
        7,
        8,
        tzinfo=timezone(-timedelta(hours=7)),
    )
    provenance_statement, provenance_parameters = bind.execute.call_args_list[3].args
    assert "status = 'FAILED'" in str(provenance_statement)
    assert "failure_reason = :cutover_failure_reason" in str(provenance_statement)
    assert provenance_parameters == [
        {
            "source_job_id": 17,
            "cutover_failure_reason": (
                "invalid_reprocessing_job_payload: quarantined during contract cutover"
            ),
            "recovered_failure_reason": (
                "invalid_reprocessing_job_payload: recovered by c166 temporal-contract correction"
            ),
        }
    ]


def test_downgrade_fails_closed_before_restoring_predecessor_constraint(monkeypatch) -> None:
    operations: list[tuple[object, ...]] = []
    monkeypatch.setattr(op, "execute", lambda statement: operations.append(("execute", statement)))
    monkeypatch.setattr(
        op,
        "drop_constraint",
        lambda name, table, **kwargs: operations.append(("drop", name, table, kwargs)),
    )
    monkeypatch.setattr(
        op,
        "create_check_constraint",
        lambda name, table, condition: operations.append(("create", name, table, condition)),
    )
    migration = runpy.run_path(str(MIGRATION))

    migration["downgrade"]()

    downgrade_guard = str(operations[0][1])
    assert "set_config('lock_timeout', '5s', true)" in downgrade_guard
    assert "ACCESS EXCLUSIVE" in downgrade_guard
    assert downgrade_guard.index("set_config") < downgrade_guard.index("LOCK TABLE")
    assert "unsupported by the predecessor constraint" in downgrade_guard
    assert operations[1][0] == "drop"
    predecessor_constraint = operations[2][3]
    assert "[+-][0-9]{2}:?[0-9]{2}" in predecessor_constraint
    assert "[T ]" not in predecessor_constraint
    assert "earliest_impacted_date' ~" not in predecessor_constraint


def test_recovery_rejects_python_or_database_temporal_mismatch() -> None:
    migration = runpy.run_path(str(MIGRATION))
    recover = migration["_recoverable_fx_parameters"]

    assert recover(_recoverable_row()) is not None
    assert recover(_recoverable_row(payload_representable=False)) is None
    assert recover(_recoverable_row(earliest_date_representable=False)) is None
    assert recover(_recoverable_row(generated_at_representable=False)) is None
    assert recover(_recoverable_row(timezone_pattern_matches=False)) is None
    oversized_integer = "1" * 5_000
    assert (
        recover(
            _recoverable_row(
                payload_json=(
                    '{"from_currency":"USD","to_currency":"SGD",'
                    '"earliest_impacted_date":"2025-01-04",'
                    '"content_hash":"sha256:aaaaaaaa",'
                    '"generated_at":"2025-01-07T08:00:00-07",'
                    f'"extension":{oversized_integer}}}'
                )
            )
        )
        is not None
    )
    assert (
        recover(
            _recoverable_row(
                payload={
                    "from_currency": "USD",
                    "to_currency": "SGD",
                    "earliest_impacted_date": "2025-01-04",
                    "content_hash": "sha256:" + ("a" * 64),
                    "generated_at": "2025-01-07T08:00:00",
                }
            )
        )
        is None
    )
