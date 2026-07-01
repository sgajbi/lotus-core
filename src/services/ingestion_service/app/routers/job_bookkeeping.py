import logging

from fastapi import HTTPException, status

from ..bookkeeping_recovery import (
    POST_BOOKKEEPING_RECOVERY_PATH,
    POST_BOOKKEEPING_REMEDIATION,
    POST_BOOKKEEPING_REPAIR_ACTION,
    bookkeeping_reason_code,
)
from ..request_metadata import get_request_lineage
from ..services.ingestion_job_service import IngestionJobService

logger = logging.getLogger(__name__)

INGESTION_JOB_BOOKKEEPING_FAILED_CODE = "INGESTION_JOB_BOOKKEEPING_FAILED"


def post_publish_bookkeeping_failure_detail(
    *,
    job_id: str,
    failure_phase: str,
    publish_state: str = "published",
    work_state: str = "published",
    published_record_count: int | None = None,
) -> dict[str, object]:
    correlation_id, request_id, trace_id = get_request_lineage()
    reason_code = bookkeeping_reason_code(failure_phase)
    detail: dict[str, object] = {
        "code": INGESTION_JOB_BOOKKEEPING_FAILED_CODE,
        "message": ("Ingestion work completed, but job bookkeeping did not complete afterward."),
        "job_id": job_id,
        "publish_state": publish_state,
        "work_state": work_state,
        "published_record_count": published_record_count,
        "retry_safe": False,
        "recovery_action": POST_BOOKKEEPING_REPAIR_ACTION,
        "recovery_path": POST_BOOKKEEPING_RECOVERY_PATH,
        "supportability_reason_code": reason_code,
        "remediation": POST_BOOKKEEPING_REMEDIATION,
    }
    if correlation_id:
        detail["correlation_id"] = correlation_id
    if request_id:
        detail["request_id"] = request_id
    if trace_id:
        detail["trace_id"] = trace_id
    return detail


async def raise_post_publish_bookkeeping_failure(
    *,
    ingestion_job_service: IngestionJobService,
    job_id: str,
    failure_reason: str,
    failure_phase: str = "queue_bookkeeping",
    publish_state: str = "published",
    work_state: str = "published",
    published_record_count: int | None = None,
) -> None:
    try:
        await ingestion_job_service.record_failure_observation(
            job_id,
            failure_reason,
            failure_phase=failure_phase,
        )
    except Exception:
        logger.exception(
            "Failed to persist ingestion bookkeeping failure observation.",
            extra={"job_id": job_id, "failure_phase": failure_phase},
        )

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=post_publish_bookkeeping_failure_detail(
            job_id=job_id,
            failure_phase=failure_phase,
            publish_state=publish_state,
            work_state=work_state,
            published_record_count=published_record_count,
        ),
    )
