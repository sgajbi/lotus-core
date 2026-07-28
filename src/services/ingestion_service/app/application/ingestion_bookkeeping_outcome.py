from __future__ import annotations

from ..bookkeeping_recovery import (
    POST_BOOKKEEPING_RECOVERY_PATH,
    POST_BOOKKEEPING_REMEDIATION,
    POST_BOOKKEEPING_REPAIR_ACTION,
    bookkeeping_reason_code,
)

INGESTION_JOB_BOOKKEEPING_FAILED_CODE = "INGESTION_JOB_BOOKKEEPING_FAILED"


def build_ingestion_bookkeeping_failure_detail(
    *,
    job_id: str,
    failure_phase: str,
    publish_state: str,
    work_state: str,
    published_record_count: int | None,
    correlation_id: str | None = None,
    request_id: str | None = None,
    trace_id: str | None = None,
) -> dict[str, object]:
    detail: dict[str, object] = {
        "code": INGESTION_JOB_BOOKKEEPING_FAILED_CODE,
        "message": "Ingestion work completed, but job bookkeeping did not complete afterward.",
        "job_id": job_id,
        "publish_state": publish_state,
        "work_state": work_state,
        "published_record_count": published_record_count,
        "retry_safe": False,
        "recovery_action": POST_BOOKKEEPING_REPAIR_ACTION,
        "recovery_path": POST_BOOKKEEPING_RECOVERY_PATH,
        "supportability_reason_code": bookkeeping_reason_code(failure_phase),
        "remediation": POST_BOOKKEEPING_REMEDIATION,
    }
    if correlation_id:
        detail["correlation_id"] = correlation_id
    if request_id:
        detail["request_id"] = request_id
    if trace_id:
        detail["trace_id"] = trace_id
    return detail
