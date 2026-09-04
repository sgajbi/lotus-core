"""Contract proof for forward-only reprocessing temporal compatibility."""

from __future__ import annotations

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
    row: dict[str, object] = {
        "id": 17,
        "payload": {
            "from_currency": "USD",
            "to_currency": "SGD",
            "earliest_impacted_date": "2025-01-04",
            "content_hash": "sha256:" + ("a" * 64),
            "generated_at": "2025-01-07T08:00:00-07",
        },
        "attempt_count": 2,
        "correlation_id": "corr-recovered",
        "correlation_missing_reason": None,
        "alternate_lookup_key": None,
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
    bind.execute.side_effect = [candidate_result, MagicMock()]
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
    assert migration["revision"] == "c166b2c3d52d"
    assert migration["down_revision"] == "c165b2c3d52c"

    migration["upgrade"]()

    assert "ACCESS EXCLUSIVE" in str(operations[0][1])
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
    assert "[+-][0-9]{2}(:?[0-9]{2}" in corrected_constraint
    model_constraint = next(
        item
        for item in ReprocessingJob.__table__.constraints
        if item.name == "ck_reprocessing_jobs_active_payload_valid"
    )
    assert _normalized_sql(corrected_constraint) == _normalized_sql(model_constraint.sqltext)

    recovery_query, query_parameters = bind.execute.call_args_list[0].args
    assert "status = 'FAILED'" in str(recovery_query)
    assert "pg_input_is_valid" in str(recovery_query)
    assert query_parameters == {
        "failure_reason": ("invalid_reprocessing_job_payload: quarantined during contract cutover")
    }
    recovery_statement, recovery_parameters = bind.execute.call_args_list[1].args
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

    assert "unsupported by the predecessor constraint" in str(operations[0][1])
    assert operations[1][0] == "drop"
    predecessor_constraint = operations[2][3]
    assert "[+-][0-9]{2}:?[0-9]{2}" in predecessor_constraint
    assert "[+-][0-9]{2}(:?[0-9]{2}" not in predecessor_constraint


def test_recovery_rejects_python_or_database_temporal_mismatch() -> None:
    migration = runpy.run_path(str(MIGRATION))
    recover = migration["_recoverable_fx_parameters"]

    assert recover(_recoverable_row()) is not None
    assert recover(_recoverable_row(earliest_date_representable=False)) is None
    assert recover(_recoverable_row(generated_at_representable=False)) is None
    assert recover(_recoverable_row(timezone_pattern_matches=False)) is None
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
