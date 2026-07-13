from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.services.query_control_plane_service.app.application.analytics.analytics_export_lifecycle import (  # noqa: E501
    export_job_is_completed,
    export_job_is_fresh,
    export_job_is_inflight,
    export_job_stale_threshold,
)
from src.services.query_control_plane_service.app.domain.analytics import AnalyticsExportJobRecord


def _export_job(
    *,
    status: str,
    updated_at: datetime | None = None,
) -> AnalyticsExportJobRecord:
    recorded_at = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)
    return AnalyticsExportJobRecord(
        job_id="aexp_1",
        dataset_type="position_timeseries",
        portfolio_id="P1",
        status=status,
        request_fingerprint="fp1",
        request_payload={},
        result_payload=None,
        result_row_count=None,
        result_format="json",
        compression="none",
        error_message=None,
        created_at=recorded_at,
        started_at=None,
        completed_at=None,
        updated_at=updated_at or recorded_at,
    )


def test_export_job_lifecycle_predicates_normalize_status() -> None:
    assert export_job_is_completed(_export_job(status=" COMPLETED "))
    assert export_job_is_inflight(_export_job(status="accepted"))
    assert export_job_is_inflight(_export_job(status=" RUNNING "))
    assert not export_job_is_inflight(_export_job(status="completed"))


def test_export_job_freshness_uses_configured_timeout() -> None:
    reference_now = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)

    assert export_job_stale_threshold(
        timeout_minutes=15,
        reference_now=reference_now,
    ) == datetime(2026, 6, 4, 11, 45, tzinfo=UTC)
    assert export_job_is_fresh(
        _export_job(status="running", updated_at=reference_now - timedelta(minutes=14)),
        timeout_minutes=15,
        reference_now=reference_now,
    )
    assert not export_job_is_fresh(
        _export_job(status="running", updated_at=reference_now - timedelta(minutes=16)),
        timeout_minutes=15,
        reference_now=reference_now,
    )
