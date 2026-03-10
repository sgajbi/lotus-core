from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone

import pytest

from tests.test_support.pipeline_quiescence import (
    format_pipeline_activity_snapshot,
    is_pipeline_quiescent,
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
        is True
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
