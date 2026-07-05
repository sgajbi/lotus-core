# services/ingestion_service/app/routers/business_dates.py
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..ack_response import build_batch_ack
from ..dependencies import get_business_date_ingestion_command_handler
from ..DTOs.business_date_dto import BusinessDateIngestionRequest
from ..DTOs.ingestion_ack_dto import BatchIngestionAcceptedResponse
from ..request_metadata import resolve_idempotency_key
from ..services.business_date_ingestion_commands import (
    BusinessDateBookkeepingFailed,
    BusinessDateIngestionCommand,
    BusinessDateIngestionCommandError,
    BusinessDateIngestionCommandHandler,
    BusinessDateIngestionPublishUnavailable,
)
from .job_bookkeeping import (
    post_publish_bookkeeping_failure_detail,
)
from .publish_errors import (
    ingestion_idempotency_conflict_response,
    ingestion_publish_failed_example,
    ingestion_unavailable_response,
    raise_ingestion_publish_unavailable,
)

logger = logging.getLogger(__name__)
router = APIRouter()

BUSINESS_DATE_MODE_BLOCKED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_MODE_BLOCKS_WRITES",
        "message": "Ingestion writes are currently disabled by operating mode.",
    }
}
BUSINESS_DATE_RATE_LIMIT_EXCEEDED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_RATE_LIMIT_EXCEEDED",
        "message": "Ingestion write rate limit exceeded for /ingest/business-dates.",
    }
}
BUSINESS_DATE_PAYLOAD_EMPTY_EXAMPLE = {
    "detail": {
        "code": "BUSINESS_DATE_PAYLOAD_EMPTY",
        "message": "At least one business_date record is required.",
    }
}
BUSINESS_DATE_FUTURE_POLICY_EXAMPLE = {
    "detail": {
        "code": "BUSINESS_DATE_FUTURE_POLICY_VIOLATION",
        "message": "business_date '2026-12-31' exceeds allowed max '2026-04-09'.",
    }
}
BUSINESS_DATE_MONOTONIC_POLICY_EXAMPLE = {
    "detail": {
        "code": "BUSINESS_DATE_MONOTONIC_POLICY_VIOLATION",
        "message": (
            "incoming max business_date '2026-01-15' for calendar_code 'SGX' is older "
            "than latest persisted '2026-01-16'."
        ),
    }
}
BUSINESS_DATE_PUBLISH_FAILED_EXAMPLE = ingestion_publish_failed_example(
    message="Failed to publish business date 'GLOBAL|2026-03-10'.",
    failed_record_keys=["GLOBAL|2026-03-10"],
    job_id="ing_01HZY3W6K8QF5B3Z7R9M2N1P0A",
)


@router.post(
    "/ingest/business-dates",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    responses={
        status.HTTP_409_CONFLICT: ingestion_idempotency_conflict_response(),
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": "Write-rate protection blocked the business-date request.",
            "content": {"application/json": {"example": BUSINESS_DATE_RATE_LIMIT_EXCEEDED_EXAMPLE}},
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Business-date payload violated validation or policy rules.",
            "content": {"application/json": {"example": BUSINESS_DATE_PAYLOAD_EMPTY_EXAMPLE}},
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: ingestion_unavailable_response(
            mode_blocked_example=BUSINESS_DATE_MODE_BLOCKED_EXAMPLE,
            publish_failed_example=BUSINESS_DATE_PUBLISH_FAILED_EXAMPLE,
        ),
    },
    tags=["Business Dates"],
    summary="Ingest business dates",
    description=(
        "What: Accept canonical business calendar dates used by valuation "
        "and processing lifecycles.\n"
        "How: Validate date records, apply ingestion controls, and publish "
        "asynchronous persistence events.\n"
        "When: Use for calendar setup, holiday updates, and date-correction operations."
    ),
)
async def ingest_business_dates(
    request: BusinessDateIngestionRequest,
    http_request: Request,
    command_handler: BusinessDateIngestionCommandHandler = Depends(
        get_business_date_ingestion_command_handler
    ),
):
    idempotency_key = resolve_idempotency_key(http_request)
    try:
        result = await command_handler.ingest_business_dates(
            BusinessDateIngestionCommand(
                request=request,
                endpoint=str(http_request.url.path),
                idempotency_key=idempotency_key,
            )
        )
    except BusinessDateIngestionCommandError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except BusinessDateIngestionPublishUnavailable as exc:
        raise_ingestion_publish_unavailable(exc.publish_error, job_id=exc.job_id)
    except BusinessDateBookkeepingFailed as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=post_publish_bookkeeping_failure_detail(
                job_id=exc.job_id,
                failure_phase=exc.failure_phase,
                publish_state=exc.publish_state,
                work_state=exc.work_state,
                published_record_count=exc.published_record_count,
            ),
        ) from exc

    if not result.replayed:
        logger.info(
            "Business dates successfully queued.",
            extra={"num_dates": result.accepted_count},
        )
    return _business_date_ack(
        message=result.message,
        job_id=result.job_id,
        accepted_count=result.accepted_count,
        idempotency_key=idempotency_key,
    )


def _business_date_ack(
    *,
    message: str,
    job_id: str,
    accepted_count: int,
    idempotency_key: str | None,
) -> BatchIngestionAcceptedResponse:
    return build_batch_ack(
        message=message,
        entity_type="business_date",
        job_id=job_id,
        accepted_count=accepted_count,
        idempotency_key=idempotency_key,
    )
