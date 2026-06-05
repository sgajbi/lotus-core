from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.services.query_service.app.services.analytics_export_results import (
    AnalyticsExportResultError,
    analytics_export_json_result_response,
    analytics_export_ndjson_result_response,
    completed_analytics_export_result_payload,
)

_DEFAULT_RESULT_PAYLOAD = object()


def _export_row(
    *,
    status: str = "completed",
    result_payload: object = _DEFAULT_RESULT_PAYLOAD,
    dataset_type: str = "portfolio_timeseries",
) -> SimpleNamespace:
    return SimpleNamespace(
        job_id="aexp_1",
        dataset_type=dataset_type,
        status=status,
        result_payload=(
            {
                "job_id": "aexp_1",
                "dataset_type": dataset_type,
                "request_fingerprint": "fp",
                "lifecycle_mode": "inline_job_execution",
                "generated_at": "2026-03-01T00:00:00Z",
                "contract_version": "rfc_063_v1",
                "result_row_count": 1,
                "data": [{"valuation_date": "2025-01-01"}],
            }
            if result_payload is _DEFAULT_RESULT_PAYLOAD
            else result_payload
        ),
    )


def test_completed_analytics_export_result_payload_rejects_incomplete_job() -> None:
    with pytest.raises(AnalyticsExportResultError) as exc_info:
        completed_analytics_export_result_payload(_export_row(status="running"))

    assert exc_info.value.code == "UNSUPPORTED_CONFIGURATION"
    assert str(exc_info.value) == "Export job is not completed yet; result unavailable."


def test_completed_analytics_export_result_payload_rejects_missing_payload() -> None:
    with pytest.raises(AnalyticsExportResultError) as exc_info:
        completed_analytics_export_result_payload(_export_row(result_payload=None))

    assert exc_info.value.code == "INSUFFICIENT_DATA"
    assert str(exc_info.value) == "Export job completed without payload."


def test_analytics_export_json_result_response_builds_dto() -> None:
    response = analytics_export_json_result_response(_export_row())

    assert response.job_id == "aexp_1"
    assert response.dataset_type == "portfolio_timeseries"
    assert response.request_fingerprint == "fp"
    assert response.result_row_count == 1
    assert response.data == [{"valuation_date": "2025-01-01"}]


def test_analytics_export_ndjson_result_response_returns_transport_tuple() -> None:
    content, media_type, content_encoding = analytics_export_ndjson_result_response(
        _export_row(dataset_type="position_timeseries"),
        compression="none",
    )

    assert media_type == "application/x-ndjson"
    assert content_encoding == "none"
    first_line = content.decode("utf-8").splitlines()[0]
    assert json.loads(first_line) == {
        "record_type": "metadata",
        "job_id": "aexp_1",
        "dataset_type": "position_timeseries",
        "generated_at": "2026-03-01T00:00:00Z",
        "contract_version": "rfc_063_v1",
    }


def test_analytics_export_ndjson_result_response_maps_malformed_payload() -> None:
    with pytest.raises(AnalyticsExportResultError) as exc_info:
        analytics_export_ndjson_result_response(
            _export_row(result_payload={"data": "bad"}),
            compression="none",
        )

    assert exc_info.value.code == "INSUFFICIENT_DATA"
    assert str(exc_info.value) == "Export payload data is malformed."
