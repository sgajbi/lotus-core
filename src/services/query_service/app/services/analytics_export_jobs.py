from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal

from portfolio_common.monitoring import (
    ANALYTICS_EXPORT_PAGE_DEPTH,
    ANALYTICS_EXPORT_RESULT_BYTES,
)

from ..dtos.analytics_input_dto import AnalyticsExportJobResponse


def analytics_export_result_endpoint(job_id: str) -> str:
    return f"/integration/exports/analytics-timeseries/jobs/{job_id}/result"


def normalize_analytics_export_job_status(status: str | None) -> str | None:
    if status is None:
        return None
    normalized_status = status.strip().lower()
    return normalized_status or None


def analytics_export_job_response(
    row: object,
    *,
    lifecycle_mode: str,
    disposition: str = "status_lookup",
) -> AnalyticsExportJobResponse:
    normalized_status = normalize_analytics_export_job_status(row.status)
    return AnalyticsExportJobResponse(
        job_id=row.job_id,
        dataset_type=row.dataset_type,
        portfolio_id=row.portfolio_id,
        status=normalized_status or row.status,
        disposition=disposition,
        lifecycle_mode=lifecycle_mode,
        request_fingerprint=row.request_fingerprint,
        result_available=normalized_status == "completed",
        result_endpoint=analytics_export_result_endpoint(row.job_id),
        result_format=row.result_format,
        compression=row.compression,
        result_row_count=row.result_row_count,
        error_message=row.error_message,
        created_at=row.created_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
    )


def reused_analytics_export_job_response(
    row: object, *, lifecycle_mode: str
) -> AnalyticsExportJobResponse:
    disposition = (
        "reused_completed"
        if normalize_analytics_export_job_status(row.status) == "completed"
        else "reused_inflight"
    )
    return analytics_export_job_response(
        row,
        lifecycle_mode=lifecycle_mode,
        disposition=disposition,
    )


def analytics_export_result_payload(
    *,
    job_id: str,
    dataset_type: str,
    request_fingerprint: str,
    lifecycle_mode: str,
    data_rows: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "job_id": job_id,
        "dataset_type": dataset_type,
        "request_fingerprint": request_fingerprint,
        "lifecycle_mode": lifecycle_mode,
        "generated_at": datetime.now(UTC).isoformat(),
        "contract_version": "rfc_063_v1",
        "result_row_count": len(data_rows),
        "data": analytics_export_jsonable(data_rows),
    }


def analytics_export_jsonable(value: object) -> object:
    if isinstance(value, Decimal):
        return _jsonable_decimal(value)
    if isinstance(value, (date, datetime)):
        return _jsonable_temporal(value)
    if isinstance(value, list):
        return _jsonable_list(value)
    if isinstance(value, dict):
        return _jsonable_dict(value)
    return value


def _jsonable_decimal(value: Decimal) -> str:
    return str(value)


def _jsonable_temporal(value: date | datetime) -> str:
    return value.isoformat()


def _jsonable_list(value: list[object]) -> list[object]:
    return [analytics_export_jsonable(item) for item in value]


def _jsonable_dict(value: dict[object, object]) -> dict[str, object]:
    return {str(key): analytics_export_jsonable(item) for key, item in value.items()}


def record_analytics_export_result_metrics(
    *,
    result_format: str,
    compression: str,
    dataset_type: str,
    result_payload: dict[str, object],
    page_depth: int,
) -> None:
    result_bytes = len(json.dumps(result_payload, separators=(",", ":")).encode("utf-8"))
    ANALYTICS_EXPORT_RESULT_BYTES.labels(result_format, compression).observe(result_bytes)
    ANALYTICS_EXPORT_PAGE_DEPTH.labels(dataset_type).observe(page_depth)
