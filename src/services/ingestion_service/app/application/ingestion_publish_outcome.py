from __future__ import annotations

INGESTION_PUBLISH_RETRY_AFTER_SECONDS = 30
INGESTION_PUBLISH_FAILED_CODE = "INGESTION_PUBLISH_FAILED"
INGESTION_PUBLISH_DEPENDENCY = "kafka"


def build_ingestion_publish_failure_detail(
    *,
    message: str,
    failed_record_keys: list[str],
    published_record_count: int,
    job_id: str | None = None,
    correlation_id: str | None = None,
    request_id: str | None = None,
    trace_id: str | None = None,
) -> dict[str, object]:
    detail: dict[str, object] = {
        "code": INGESTION_PUBLISH_FAILED_CODE,
        "message": message,
        "dependency": INGESTION_PUBLISH_DEPENDENCY,
        "retryable": True,
        "retry_after_seconds": INGESTION_PUBLISH_RETRY_AFTER_SECONDS,
        "publish_state": "partial" if published_record_count else "unpublished",
        "published_record_count": published_record_count,
        "failed_record_keys": list(failed_record_keys),
    }
    if job_id:
        detail["job_id"] = job_id
    if correlation_id:
        detail["correlation_id"] = correlation_id
    if request_id:
        detail["request_id"] = request_id
    if trace_id:
        detail["trace_id"] = trace_id
    return detail
