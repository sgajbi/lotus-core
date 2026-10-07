from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from src.services.ingestion_service.app.services.ingestion_slo_status import (
    IngestionSloSnapshot,
    build_slo_status_response,
    load_slo_status_response,
    slo_snapshot_from_jobs,
)


@dataclass(slots=True)
class _Job:
    status: str
    submitted_at: datetime
    completed_at: datetime | None = None


def test_slo_snapshot_from_jobs_derives_fallback_metrics():
    now = datetime(2026, 6, 5, 12, 0, tzinfo=UTC)
    jobs = [
        _Job("failed", now - timedelta(seconds=50), now - timedelta(seconds=20)),
        _Job("completed", now - timedelta(seconds=40), now - timedelta(seconds=10)),
        _Job("queued", now - timedelta(seconds=90)),
        _Job("accepted", now - timedelta(seconds=120)),
    ]

    snapshot = slo_snapshot_from_jobs(jobs=jobs, now=now)

    assert snapshot.total_jobs == 3
    assert snapshot.failed_jobs == 1
    assert snapshot.p95_latency_seconds == 30.0
    assert snapshot.backlog_age_seconds == 120.0


def test_build_slo_status_response_applies_thresholds():
    response = build_slo_status_response(
        lookback_minutes=60,
        snapshot=IngestionSloSnapshot(
            total_jobs=10,
            failed_jobs=1,
            p95_latency_seconds=7.5,
            backlog_age_seconds=360.0,
        ),
        failure_rate_threshold=Decimal("0.03"),
        queue_latency_threshold_seconds=5.0,
        backlog_age_threshold_seconds=300.0,
    )

    assert response.lookback_minutes == 60
    assert response.failure_rate == Decimal("0.1")
    assert response.breach_failure_rate is True
    assert response.breach_queue_latency is True
    assert response.breach_backlog_age is True


def test_build_slo_status_response_handles_empty_snapshot():
    response = build_slo_status_response(
        lookback_minutes=15,
        snapshot=IngestionSloSnapshot(
            total_jobs=0,
            failed_jobs=0,
            p95_latency_seconds=0.0,
            backlog_age_seconds=0.0,
        ),
        failure_rate_threshold=Decimal("0.03"),
        queue_latency_threshold_seconds=5.0,
        backlog_age_threshold_seconds=300.0,
    )

    assert response.failure_rate == Decimal("0")
    assert response.breach_failure_rate is False
    assert response.breach_queue_latency is False
    assert response.breach_backlog_age is False


@pytest.mark.parametrize("scenario", ["mixed", "all_sync", "no_completion", "async_completed"])
def test_synchronous_completion_cannot_dilute_async_queue_latency(scenario):
    now = datetime(2026, 6, 5, 12, 0, tzinfo=UTC)
    sync = [
        _Job("completed", now - timedelta(seconds=2), now - timedelta(seconds=1))
        for _ in range(1000)
    ]
    asynchronous = [
        _Job(status, now - timedelta(seconds=500), now - timedelta(seconds=100))
        for status in ("queued", "failed")
        for _ in range(5)
    ]
    pending = [
        _Job(status, now - timedelta(seconds=500)) for status in ("accepted", "queued", "failed")
    ]
    jobs = {
        "mixed": sync + asynchronous,
        "all_sync": sync,
        "no_completion": pending,
        "async_completed": asynchronous,
    }[scenario]
    before = [(job.status, job.submitted_at, job.completed_at) for job in jobs]
    snapshot = slo_snapshot_from_jobs(jobs=jobs, now=now)
    assert snapshot.total_jobs == sum(job.status != "completed" for job in jobs)
    assert snapshot.failed_jobs == (
        5 if scenario in ("mixed", "async_completed") else int(scenario == "no_completion")
    )
    assert snapshot.p95_latency_seconds == (
        400.0 if scenario in ("mixed", "async_completed") else 0.0
    )
    assert snapshot.backlog_age_seconds == (0.0 if scenario == "all_sync" else 500.0)
    assert [(job.status, job.submitted_at, job.completed_at) for job in jobs] == before


@pytest.mark.parametrize("sync_count", [0, 1, 1000])
def test_async_failure_cohort_is_invariant_to_synchronous_success(sync_count):
    now = datetime(2026, 6, 5, 12, 0, tzinfo=UTC)
    asynchronous = [
        _Job(status, now - timedelta(seconds=500), now - timedelta(seconds=100))
        for status in ("accepted", "queued", "failed")
    ]
    sync = [_Job("completed", now, now) for _ in range(sync_count)]
    jobs = asynchronous + sync
    before = list(jobs)
    snapshot = slo_snapshot_from_jobs(jobs=jobs, now=now)
    assert snapshot == slo_snapshot_from_jobs(jobs=asynchronous, now=now)
    response = build_slo_status_response(
        lookback_minutes=60,
        snapshot=snapshot,
        failure_rate_threshold=Decimal("0.03"),
        queue_latency_threshold_seconds=5.0,
        backlog_age_threshold_seconds=300.0,
    )
    assert response.total_jobs == 3 and response.failed_jobs == 1
    assert response.failure_rate == Decimal(1) / Decimal(3)
    assert response.breach_failure_rate
    assert response.p95_queue_latency_seconds == 400.0 and response.backlog_age_seconds == 500.0
    assert jobs == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "availability",
    ["no_session", "aggregate_empty", "fallback_empty", "unavailable", "fallback_records"],
)
async def test_slo_query_recovery_defaults_and_metric_publication(availability):
    now = datetime.now(UTC)
    aggregate_error = SQLAlchemyError("synthetic aggregate unavailable")
    fallback_error = SQLAlchemyError("synthetic fallback unavailable")
    jobs = [_Job("failed", now - timedelta(seconds=70), now - timedelta(seconds=10))]
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(one=lambda: (None, None, None, None))),
        scalars=AsyncMock(
            return_value=SimpleNamespace(
                all=lambda: jobs if availability == "fallback_records" else []
            )
        ),
    )
    if availability in {"fallback_empty", "unavailable", "fallback_records"}:
        db.execute.side_effect = aggregate_error
    if availability == "unavailable":
        db.scalars.side_effect = fallback_error

    async def sessions():
        if availability != "no_session":
            yield db

    metric, logger = Mock(), Mock()
    response = await load_slo_status_response(
        lookback_minutes=15,
        failure_rate_threshold=Decimal("0.03"),
        queue_latency_threshold_seconds=5.0,
        backlog_age_threshold_seconds=300.0,
        session_factory=sessions,
        backlog_age_metric=metric,
        logger=logger,
    )
    assert response.lookback_minutes == 15
    if availability == "fallback_records":
        assert response.total_jobs == response.failed_jobs == 1
        assert response.failure_rate == Decimal("1")
        assert response.p95_queue_latency_seconds == 60.0
        assert response.breach_failure_rate and response.breach_queue_latency
    else:
        assert response.total_jobs == response.failed_jobs == 0
        assert response.failure_rate == Decimal("0")
        assert response.p95_queue_latency_seconds == response.backlog_age_seconds == 0.0
        assert not response.breach_failure_rate and not response.breach_queue_latency
    assert not response.breach_backlog_age
    if availability in {"no_session", "unavailable"}:
        metric.set.assert_not_called()
    else:
        metric.set.assert_called_once_with(0.0)
    if availability == "unavailable":
        logger.warning.assert_called_once_with(
            "ingestion_slo_status_fallback_unavailable",
            extra={"lookback_minutes": 15},
            exc_info=fallback_error,
        )
    else:
        logger.warning.assert_not_called()
    if availability == "no_session":
        db.execute.assert_not_awaited()
    if availability in {"fallback_empty", "unavailable", "fallback_records"}:
        db.scalars.assert_awaited_once()
    else:
        db.scalars.assert_not_awaited()
