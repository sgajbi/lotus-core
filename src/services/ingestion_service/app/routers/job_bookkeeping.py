import logging

from fastapi import HTTPException, status

from ..services.ingestion_job_service import IngestionJobService

logger = logging.getLogger(__name__)


async def raise_post_publish_bookkeeping_failure(
    *,
    ingestion_job_service: IngestionJobService,
    job_id: str,
    failure_reason: str,
    failure_phase: str = "queue_bookkeeping",
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
        detail={
            "code": "INGESTION_JOB_BOOKKEEPING_FAILED",
            "message": (
                "Ingestion publish or persist work completed, but job bookkeeping failed "
                f"afterward: {failure_reason}"
            ),
            "job_id": job_id,
        },
    )
