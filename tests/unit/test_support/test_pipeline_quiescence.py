from __future__ import annotations

from collections import deque
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.engine import make_url

from tests.test_support.db_cleanup import (
    DatabaseCleanupAuthorization,
    DatabaseCleanupAuthorizationError,
    authorize_database_cleanup,
)
from tests.test_support.pipeline_quiescence import (
    format_pipeline_activity_snapshot,
    has_only_reprocessing_activity,
    is_pipeline_quiescent,
    read_pipeline_last_activity_at,
    recover_reprocessing_activity_for_test_cleanup,
    wait_for_pipeline_quiescence,
)
from tests.test_support.runtime_env import PreparedTestRuntime, prepare_test_runtime


def _authorize_cleanup(
    engine: MagicMock,
) -> tuple[PreparedTestRuntime, DatabaseCleanupAuthorization]:
    runtime = prepare_test_runtime(
        profile="integration",
        scope="recovery-authorization",
        env={"LOTUS_TEST_DYNAMIC_PORTS": "true"},
        preserve_existing=False,
        inherit_process_environment=False,
    )
    engine.url = make_url(runtime.endpoints.host_database_url)
    return runtime, authorize_database_cleanup(runtime=runtime, engine=engine)


def test_is_pipeline_quiescent_requires_all_zero_counts() -> None:
    assert is_pipeline_quiescent({"outbox_pending": 0, "ingestion_backlog": 0}) is True
    assert is_pipeline_quiescent({"outbox_pending": 1, "ingestion_backlog": 0}) is False
    assert (
        is_pipeline_quiescent(
            {
                "outbox_pending": 0,
                "ingestion_backlog": 0,
                "aggregation_jobs_active": 3,
                "pipeline_stage_pending": 7,
            }
        )
        is True
    )
    assert (
        is_pipeline_quiescent(
            {
                "outbox_pending": 0,
                "ingestion_backlog": 0,
                "position_state_reprocessing": 3,
                "instrument_reprocessing_active": 2,
            }
        )
        is False
    )


def test_format_pipeline_activity_snapshot_is_stable() -> None:
    assert format_pipeline_activity_snapshot({"b": 2, "a": 1}) == "a=1, b=2"


def test_has_only_reprocessing_activity_identifies_recoverable_snapshot() -> None:
    assert has_only_reprocessing_activity(
        {
            "reprocessing_jobs_active": 1,
            "position_state_reprocessing": 0,
            "instrument_reprocessing_active": 0,
            "outbox_pending": 0,
        }
    )
    assert not has_only_reprocessing_activity(
        {
            "reprocessing_jobs_active": 1,
            "position_state_reprocessing": 0,
            "instrument_reprocessing_active": 0,
            "outbox_pending": 2,
        }
    )
    assert not has_only_reprocessing_activity({"outbox_pending": 0, "ingestion_backlog": 0})


def test_wait_for_pipeline_quiescence_requires_stable_zero_snapshots(monkeypatch) -> None:
    snapshots = deque(
        [
            {"outbox_pending": 2, "ingestion_backlog": 0},
            {"outbox_pending": 0, "ingestion_backlog": 0},
            {"outbox_pending": 1, "ingestion_backlog": 0},
            {"outbox_pending": 0, "ingestion_backlog": 0},
            {"outbox_pending": 0, "ingestion_backlog": 0},
        ]
    )

    monkeypatch.setattr("tests.test_support.pipeline_quiescence.time.sleep", lambda _: None)
    monkeypatch.setattr(
        "tests.test_support.pipeline_quiescence.time.time",
        lambda: 0,
    )

    result = wait_for_pipeline_quiescence(
        timeout_seconds=10,
        poll_seconds=0,
        stable_cycles=2,
        snapshot_reader=lambda: snapshots.popleft(),
    )

    assert result == {"outbox_pending": 0, "ingestion_backlog": 0}


def test_wait_for_pipeline_quiescence_does_not_bypass_quiet_window_without_active_rows(
    monkeypatch,
) -> None:
    snapshot = {"outbox_pending": 0, "ingestion_backlog": 0}
    times = iter((0, 0, 0, 1, 1, 4, 4, 8, 8))
    reads = 0

    def _read_snapshot() -> dict[str, int]:
        nonlocal reads
        reads += 1
        return snapshot

    monkeypatch.setattr("tests.test_support.pipeline_quiescence.time.sleep", lambda _: None)
    monkeypatch.setattr(
        "tests.test_support.pipeline_quiescence.time.time",
        lambda: next(times),
    )

    result = wait_for_pipeline_quiescence(
        timeout_seconds=10,
        poll_seconds=0,
        stable_cycles=1,
        quiet_seconds=8,
        snapshot_reader=_read_snapshot,
        last_activity_reader=lambda: None,
    )

    assert result == snapshot
    assert reads == 3


def test_wait_for_pipeline_quiescence_restarts_zero_timer_after_observed_activity(
    monkeypatch,
) -> None:
    snapshot = {"outbox_pending": 0, "ingestion_backlog": 0}
    times = iter((0, 0, 0, 1, 1, 4, 4, 9))
    activity_times = iter((datetime(2020, 1, 1), None, None))
    reads = 0

    def _read_snapshot() -> dict[str, int]:
        nonlocal reads
        reads += 1
        return snapshot

    monkeypatch.setattr("tests.test_support.pipeline_quiescence.time.sleep", lambda _: None)
    monkeypatch.setattr(
        "tests.test_support.pipeline_quiescence.time.time",
        lambda: next(times),
    )

    result = wait_for_pipeline_quiescence(
        timeout_seconds=10,
        poll_seconds=0,
        stable_cycles=1,
        quiet_seconds=8,
        snapshot_reader=_read_snapshot,
        last_activity_reader=lambda: next(activity_times),
    )

    assert result == snapshot
    assert reads == 3


def test_wait_for_pipeline_quiescence_times_out_with_last_snapshot(monkeypatch) -> None:
    snapshots = deque(
        [
            {"outbox_pending": 1, "ingestion_backlog": 0},
            {"outbox_pending": 1, "ingestion_backlog": 3},
        ]
    )
    times = deque([0, 1, 2, 3, 4, 5, 6])

    monkeypatch.setattr("tests.test_support.pipeline_quiescence.time.sleep", lambda _: None)
    monkeypatch.setattr(
        "tests.test_support.pipeline_quiescence.time.time",
        lambda: times.popleft(),
    )

    with pytest.raises(TimeoutError, match="outbox_pending=1"):
        wait_for_pipeline_quiescence(
            timeout_seconds=5,
            poll_seconds=0,
            stable_cycles=2,
            snapshot_reader=lambda: snapshots[0] if len(snapshots) == 1 else snapshots.popleft(),
        )


def test_read_pipeline_last_activity_at_ignores_non_blocking_tables() -> None:
    engine = MagicMock()
    connection = MagicMock()
    engine.connect.return_value.__enter__.return_value = connection
    connection.execute.side_effect = [
        MagicMock(
            fetchall=MagicMock(
                return_value=[
                    ("outbox_events",),
                    ("portfolio_aggregation_jobs",),
                    ("position_state",),
                ]
            )
        ),
        MagicMock(
            fetchall=MagicMock(
                return_value=[
                    ("outbox_events", "updated_at"),
                    ("portfolio_aggregation_jobs", "updated_at"),
                    ("position_state", "updated_at"),
                ]
            )
        ),
        MagicMock(scalar=MagicMock(return_value=datetime(2026, 3, 12, 10, 0))),
    ]

    last_activity_at = read_pipeline_last_activity_at(engine)

    assert last_activity_at is not None
    assert last_activity_at.isoformat() == "2026-03-12T10:00:00+00:00"
    union_sql = str(connection.execute.call_args_list[-1][0][0])
    assert "outbox_events" in union_sql
    assert "portfolio_aggregation_jobs" not in union_sql
    assert "position_state" in union_sql
    assert "status = 'PENDING'" in union_sql or "status = 'REPROCESSING'" in union_sql


def test_recover_reprocessing_activity_for_test_cleanup_resets_only_replay_tables() -> None:
    engine = MagicMock()
    runtime, authorization = _authorize_cleanup(engine)
    connection = MagicMock()
    engine.connect.return_value.__enter__.return_value = connection
    engine.begin.return_value.__enter__.return_value = connection
    connection.execute.side_effect = [
        MagicMock(
            fetchall=MagicMock(
                return_value=[
                    ("reprocessing_jobs",),
                    ("position_state",),
                    ("instrument_reprocessing_state",),
                ]
            )
        ),
        MagicMock(
            scalar=MagicMock(return_value=1),
        ),
        MagicMock(
            scalar=MagicMock(return_value=0),
        ),
        MagicMock(
            scalar=MagicMock(return_value=0),
        ),
        MagicMock(
            fetchall=MagicMock(
                return_value=[
                    ("reprocessing_jobs",),
                    ("position_state",),
                    ("instrument_reprocessing_state",),
                ]
            )
        ),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    ]

    try:
        snapshot = recover_reprocessing_activity_for_test_cleanup(
            engine,
            authorization=authorization,
        )

        assert snapshot["reprocessing_jobs_active"] == 1
        executed_sql = [str(call.args[0]) for call in connection.execute.call_args_list]
        assert any("UPDATE reprocessing_jobs" in sql for sql in executed_sql)
        assert any("UPDATE position_state" in sql for sql in executed_sql)
        assert any("DELETE FROM instrument_reprocessing_state" in sql for sql in executed_sql)
    finally:
        runtime.port_reservation.release()


def test_recover_reprocessing_activity_for_test_cleanup_is_noop_for_nonrecoverable_snapshot() -> (
    None
):
    engine = MagicMock()
    runtime, authorization = _authorize_cleanup(engine)
    connection = MagicMock()
    engine.connect.return_value.__enter__.return_value = connection
    connection.execute.side_effect = [
        MagicMock(
            fetchall=MagicMock(
                return_value=[
                    ("reprocessing_jobs",),
                    ("outbox_events",),
                ]
            )
        ),
        MagicMock(scalar=MagicMock(return_value=2)),
        MagicMock(scalar=MagicMock(return_value=1)),
    ]

    try:
        snapshot = recover_reprocessing_activity_for_test_cleanup(
            engine,
            authorization=authorization,
        )

        assert snapshot["reprocessing_jobs_active"] == 1
        assert snapshot["outbox_pending"] == 2
        assert not engine.begin.called
    finally:
        runtime.port_reservation.release()


def test_recovery_refuses_different_engine_before_read_or_mutation() -> None:
    authorized_engine = MagicMock()
    runtime, authorization = _authorize_cleanup(authorized_engine)
    drifted_engine = MagicMock()
    drifted_engine.url = make_url("postgresql://user:password@localhost:55432/shared")
    try:
        with pytest.raises(
            DatabaseCleanupAuthorizationError,
            match="delegated engine target differs",
        ):
            recover_reprocessing_activity_for_test_cleanup(
                drifted_engine,
                authorization=authorization,
            )
        assert not drifted_engine.connect.called
        assert not drifted_engine.begin.called
    finally:
        runtime.port_reservation.release()


def test_recovery_refuses_retired_runtime_generation_before_read_or_mutation() -> None:
    engine = MagicMock()
    runtime, authorization = _authorize_cleanup(engine)
    try:
        runtime.port_reservation.reallocate()
        with pytest.raises(
            DatabaseCleanupAuthorizationError,
            match="stale for the current runtime generation or target",
        ):
            recover_reprocessing_activity_for_test_cleanup(
                engine,
                authorization=authorization,
            )
        assert not engine.connect.called
        assert not engine.begin.called
    finally:
        runtime.port_reservation.release()


def test_recovery_revalidates_authority_after_activity_read_before_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = MagicMock()
    runtime, authorization = _authorize_cleanup(engine)

    def _read_then_reallocate(_engine: MagicMock) -> dict[str, int]:
        runtime.port_reservation.reallocate()
        return {"reprocessing_jobs_active": 1}

    monkeypatch.setattr(
        "tests.test_support.pipeline_quiescence.read_pipeline_activity_snapshot",
        _read_then_reallocate,
    )
    try:
        with pytest.raises(
            DatabaseCleanupAuthorizationError,
            match="stale for the current runtime generation or target",
        ):
            recover_reprocessing_activity_for_test_cleanup(
                engine,
                authorization=authorization,
            )
        assert not engine.begin.called
    finally:
        runtime.port_reservation.release()


def test_recovery_revalidates_authority_after_table_discovery_before_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = MagicMock()
    runtime, authorization = _authorize_cleanup(engine)
    connection = MagicMock()
    engine.begin.return_value.__enter__.return_value = connection

    def _discover_then_reallocate(_statement: object) -> MagicMock:
        runtime.port_reservation.reallocate()
        return MagicMock(
            fetchall=MagicMock(
                return_value=[
                    ("reprocessing_jobs",),
                    ("position_state",),
                    ("instrument_reprocessing_state",),
                ]
            )
        )

    connection.execute.side_effect = _discover_then_reallocate
    monkeypatch.setattr(
        "tests.test_support.pipeline_quiescence.read_pipeline_activity_snapshot",
        lambda _engine: {"reprocessing_jobs_active": 1},
    )
    try:
        with pytest.raises(
            DatabaseCleanupAuthorizationError,
            match="stale for the current runtime generation or target",
        ):
            recover_reprocessing_activity_for_test_cleanup(
                engine,
                authorization=authorization,
            )

        executed_sql = [str(call.args[0]) for call in connection.execute.call_args_list]
        assert len(executed_sql) == 1
        assert "FROM pg_tables" in executed_sql[0]
        assert not any("UPDATE" in sql or "DELETE" in sql for sql in executed_sql)
    finally:
        runtime.port_reservation.release()
