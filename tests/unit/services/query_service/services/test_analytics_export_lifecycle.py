from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from src.services.query_service.app.services.analytics_export_lifecycle import (
    export_job_is_completed,
    export_job_is_fresh,
    export_job_is_inflight,
    export_job_stale_threshold,
)


def test_export_job_lifecycle_predicates_normalize_status() -> None:
    assert export_job_is_completed(SimpleNamespace(status=" COMPLETED "))
    assert export_job_is_inflight(SimpleNamespace(status="accepted"))
    assert export_job_is_inflight(SimpleNamespace(status=" RUNNING "))
    assert not export_job_is_inflight(SimpleNamespace(status="completed"))


def test_export_job_freshness_uses_configured_timeout() -> None:
    reference_now = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)

    assert export_job_stale_threshold(
        timeout_minutes=15,
        reference_now=reference_now,
    ) == datetime(2026, 6, 4, 11, 45, tzinfo=UTC)
    assert export_job_is_fresh(
        SimpleNamespace(updated_at=reference_now - timedelta(minutes=14)),
        timeout_minutes=15,
        reference_now=reference_now,
    )
    assert not export_job_is_fresh(
        SimpleNamespace(updated_at=reference_now - timedelta(minutes=16)),
        timeout_minutes=15,
        reference_now=reference_now,
    )
    assert not export_job_is_fresh(
        SimpleNamespace(updated_at=None),
        timeout_minutes=15,
        reference_now=reference_now,
    )
