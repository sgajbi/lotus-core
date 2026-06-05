from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.services.query_service.app.services.analytics_export_jobs import (
    analytics_export_job_response,
    analytics_export_jsonable,
    analytics_export_result_endpoint,
    analytics_export_result_payload,
    normalize_analytics_export_job_status,
    reused_analytics_export_job_response,
)


def _export_row(*, status: str) -> SimpleNamespace:
    return SimpleNamespace(
        job_id="aexp_1",
        dataset_type="portfolio_timeseries",
        portfolio_id="P1",
        status=status,
        request_fingerprint="fp",
        result_format="json",
        compression="none",
        result_row_count=2,
        error_message=None,
        created_at=datetime(2026, 3, 1, tzinfo=UTC),
        started_at=datetime(2026, 3, 1, tzinfo=UTC),
        completed_at=datetime(2026, 3, 1, tzinfo=UTC),
    )


def test_analytics_export_job_response_normalizes_status_and_endpoint() -> None:
    response = analytics_export_job_response(
        _export_row(status=" Completed "),
        lifecycle_mode="inline_job_execution",
    )

    assert response.status == "completed"
    assert response.result_available is True
    assert response.disposition == "status_lookup"
    assert response.lifecycle_mode == "inline_job_execution"
    assert response.result_endpoint == analytics_export_result_endpoint("aexp_1")


def test_reused_analytics_export_job_response_sets_disposition() -> None:
    completed = reused_analytics_export_job_response(
        _export_row(status="completed"),
        lifecycle_mode="inline_job_execution",
    )
    inflight = reused_analytics_export_job_response(
        _export_row(status="running"),
        lifecycle_mode="inline_job_execution",
    )

    assert completed.disposition == "reused_completed"
    assert inflight.disposition == "reused_inflight"


def test_normalize_analytics_export_job_status_handles_blank_values() -> None:
    assert normalize_analytics_export_job_status(None) is None
    assert normalize_analytics_export_job_status("  ") is None
    assert normalize_analytics_export_job_status(" Running ") == "running"


def test_analytics_export_result_payload_converts_rows_to_jsonable_values() -> None:
    payload = analytics_export_result_payload(
        job_id="aexp_1",
        dataset_type="portfolio_timeseries",
        request_fingerprint="fp",
        lifecycle_mode="inline_job_execution",
        data_rows=[
            {
                "amount": Decimal("1.23"),
                "as_of_date": date(2025, 1, 1),
                "nested": [Decimal("2.00")],
            }
        ],
    )

    assert payload["job_id"] == "aexp_1"
    assert payload["result_row_count"] == 1
    assert payload["data"] == [
        {
            "amount": "1.23",
            "as_of_date": "2025-01-01",
            "nested": ["2.00"],
        }
    ]


def test_analytics_export_jsonable_normalizes_dictionary_keys() -> None:
    assert analytics_export_jsonable({1: Decimal("1.00")}) == {"1": "1.00"}
