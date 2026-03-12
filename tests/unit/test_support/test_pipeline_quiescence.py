from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from tests.test_support.pipeline_quiescence import (
    format_pipeline_activity_snapshot,
    is_pipeline_quiescent,
    read_pipeline_last_activity_at,
    wait_for_pipeline_quiescence,
)


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
    assert (
        format_pipeline_activity_snapshot({"b": 2, "a": 1})
        == "a=1, b=2"
    )


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


def test_wait_for_pipeline_quiescence_requires_quiet_window(monkeypatch) -> None:
    snapshots = deque(
        [
            {"outbox_pending": 0, "ingestion_backlog": 0},
            {"outbox_pending": 0, "ingestion_backlog": 0},
            {"outbox_pending": 0, "ingestion_backlog": 0},
        ]
    )
    now = datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc)
    activity_times = deque(
        [
            now - timedelta(seconds=2),
            now - timedelta(seconds=4),
            now - timedelta(seconds=9),
        ]
    )

    monkeypatch.setattr("tests.test_support.pipeline_quiescence.time.sleep", lambda _: None)

    class _FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now if tz is None else now.astimezone(tz)

    monkeypatch.setattr("tests.test_support.pipeline_quiescence.datetime", _FixedDateTime)
    monkeypatch.setattr("tests.test_support.pipeline_quiescence.time.time", lambda: 0)

    result = wait_for_pipeline_quiescence(
        timeout_seconds=10,
        poll_seconds=0,
        stable_cycles=1,
        quiet_seconds=8,
        snapshot_reader=lambda: snapshots.popleft(),
        last_activity_reader=lambda: activity_times.popleft(),
    )

    assert result == {"outbox_pending": 0, "ingestion_backlog": 0}


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
