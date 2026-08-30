import logging

from fastapi import HTTPException, status

from ..application.ingestion_bookkeeping_outcome import (
    build_ingestion_bookkeeping_failure_detail,
)
from ..request_metadata import get_request_lineage
from ..services.ingestion_job_service import IngestionJobService

logger = logging.getLogger(__name__)


def post_publish_bookkeeping_failure_detail(
    *,
    job_id: str,
    failure_phase: str,
    publish_state: str = "published",
    work_state: str = "published",
    published_record_count: int | None = None,
) -> dict[str, object]:
    correlation_id, request_id, trace_id = get_request_lineage()
    return build_ingestion_bookkeeping_failure_detail(
        job_id=job_id,
        failure_phase=failure_phase,
        publish_state=publish_state,
        work_state=work_state,
        published_record_count=published_record_count,
        correlation_id=correlation_id,
        request_id=request_id,
        trace_id=trace_id,
    )


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


async def mark_job_queued_after_publish_or_raise(
    *,
    ingestion_job_service: IngestionJobService,
    job_id: str,
    tenant_id: str,
    failure_phase: str = "queue_bookkeeping",
    publish_state: str = "published",
    work_state: str = "published",
    published_record_count: int | None = None,
) -> None:
    try:
        queued = await ingestion_job_service.mark_queued(job_id, tenant_id=tenant_id)
    except Exception as exc:
        await raise_post_publish_bookkeeping_failure(
            ingestion_job_service=ingestion_job_service,
            job_id=job_id,
            failure_reason=str(exc),
            failure_phase=failure_phase,
            publish_state=publish_state,
            work_state=work_state,
            published_record_count=published_record_count,
        )
        return

    if not queued:
        await raise_post_publish_bookkeeping_failure(
            ingestion_job_service=ingestion_job_service,
            job_id=job_id,
            failure_reason="job queue transition was rejected",
            failure_phase=failure_phase,
            publish_state=publish_state,
            work_state=work_state,
            published_record_count=published_record_count,
        )
