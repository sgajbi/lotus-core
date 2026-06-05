from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from src.services.ingestion_service.app.services.ingestion_slo_status import (
    IngestionSloSnapshot,
    build_slo_status_response,
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

    assert snapshot.total_jobs == 4
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
