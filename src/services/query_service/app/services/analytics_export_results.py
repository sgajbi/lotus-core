from __future__ import annotations

from ..dtos.analytics_input_dto import AnalyticsExportJsonResultResponse
from .analytics_export_jobs import normalize_analytics_export_job_status
from .analytics_export_ndjson import (
    AnalyticsExportNdjsonError,
    analytics_export_ndjson_result,
)


class AnalyticsExportResultError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def completed_analytics_export_result_payload(row: object) -> dict[str, object]:
    if normalize_analytics_export_job_status(row.status) != "completed":
        raise AnalyticsExportResultError(
            "UNSUPPORTED_CONFIGURATION",
            "Export job is not completed yet; result unavailable.",
        )
    if not isinstance(row.result_payload, dict):
        raise AnalyticsExportResultError(
            "INSUFFICIENT_DATA",
            "Export job completed without payload.",
        )
    return row.result_payload


def analytics_export_json_result_response(
    row: object,
) -> AnalyticsExportJsonResultResponse:
    return AnalyticsExportJsonResultResponse(**completed_analytics_export_result_payload(row))


def analytics_export_ndjson_result_response(
    row: object, *, compression: str
) -> tuple[bytes, str, str]:
    result_payload = completed_analytics_export_result_payload(row)
    try:
        result = analytics_export_ndjson_result(
            job_id=row.job_id,
            dataset_type=row.dataset_type,
            result_payload=result_payload,
            compression=compression,
        )
    except AnalyticsExportNdjsonError as exc:
        raise AnalyticsExportResultError("INSUFFICIENT_DATA", str(exc)) from exc
    return (result.content, result.media_type, result.content_encoding)
