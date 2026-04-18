# services/ingestion_service/app/routers/business_dates.py
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from portfolio_common.config import (
    BUSINESS_DATE_ENFORCE_MONOTONIC_ADVANCE,
    BUSINESS_DATE_MAX_FUTURE_DAYS,
)

from ..ack_response import build_batch_ack
from ..DTOs.business_date_dto import BusinessDateIngestionRequest
from ..DTOs.ingestion_ack_dto import BatchIngestionAcceptedResponse
from ..ops_controls import enforce_ingestion_write_rate_limit
from ..repositories.business_calendar_repository import (
    BusinessCalendarRepository,
    get_business_calendar_repository,
)
from ..request_metadata import (
    create_ingestion_job_id,
    get_request_lineage,
    resolve_idempotency_key,
)
from ..services.ingestion_job_service import IngestionJobService, get_ingestion_job_service
from ..services.ingestion_service import (
    IngestionPublishError,
    IngestionService,
    get_ingestion_service,
)
from .job_bookkeeping import raise_post_publish_bookkeeping_failure

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
BUSINESS_DATE_PUBLISH_FAILED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_PUBLISH_FAILED",
        "message": "Failed to publish business date 'GLOBAL|2026-03-10'.",
        "failed_record_keys": ["GLOBAL|2026-03-10"],
        "job_id": "ing_01HZY3W6K8QF5B3Z7R9M2N1P0A",
    }
}


@router.post(
    "/ingest/business-dates",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    responses={
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": "Write-rate protection blocked the business-date request.",
            "content": {"application/json": {"example": BUSINESS_DATE_RATE_LIMIT_EXCEEDED_EXAMPLE}},
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Business-date payload violated validation or policy rules.",
            "content": {"application/json": {"example": BUSINESS_DATE_PAYLOAD_EMPTY_EXAMPLE}},
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Business-date publish failed after job metadata was recorded.",
            "content": {"application/json": {"example": BUSINESS_DATE_PUBLISH_FAILED_EXAMPLE}},
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "Ingestion operating mode blocked writes.",
            "content": {"application/json": {"example": BUSINESS_DATE_MODE_BLOCKED_EXAMPLE}},
        },
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
    ingestion_service: IngestionService = Depends(get_ingestion_service),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
    business_calendar_repository: BusinessCalendarRepository = Depends(
        get_business_calendar_repository
    ),
):
    idempotency_key = resolve_idempotency_key(http_request)
    try:
        await ingestion_job_service.assert_ingestion_writable()
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "INGESTION_MODE_BLOCKS_WRITES", "message": str(exc)},
        ) from exc
    try:
        enforce_ingestion_write_rate_limit(
            endpoint="/ingest/business-dates", record_count=len(request.business_dates)
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "INGESTION_RATE_LIMIT_EXCEEDED", "message": str(exc)},
        ) from exc

    if not request.business_dates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=BUSINESS_DATE_PAYLOAD_EMPTY_EXAMPLE["detail"],
        )

    max_allowed_date = datetime.now(UTC).date() + timedelta(days=BUSINESS_DATE_MAX_FUTURE_DAYS)
    for row in request.business_dates:
        if row.business_date > max_allowed_date:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "code": "BUSINESS_DATE_FUTURE_POLICY_VIOLATION",
                    "message": (
                        f"business_date '{row.business_date.isoformat()}' exceeds "
                        f"allowed max '{max_allowed_date.isoformat()}'."
                    ),
                },
            )

    if BUSINESS_DATE_ENFORCE_MONOTONIC_ADVANCE:
        calendar_codes = {row.calendar_code for row in request.business_dates}
        for calendar_code in calendar_codes:
            latest_persisted = await business_calendar_repository.get_latest_business_date(
                calendar_code
            )
            if latest_persisted is None:
                continue
            incoming_max = max(
                row.business_date
                for row in request.business_dates
                if row.calendar_code == calendar_code
            )
            if incoming_max < latest_persisted:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "code": "BUSINESS_DATE_MONOTONIC_POLICY_VIOLATION",
                        "message": (
                            f"incoming max business_date '{incoming_max.isoformat()}' for "
                            f"calendar_code '{calendar_code}' is older than latest persisted "
                            f"'{latest_persisted.isoformat()}'."
                        ),
                    },
                )
    num_dates = len(request.business_dates)
    job_id = create_ingestion_job_id()
    correlation_id, request_id, trace_id = get_request_lineage()
    job_result = await ingestion_job_service.create_or_get_job(
        job_id=job_id,
        endpoint=str(http_request.url.path),
        entity_type="business_date",
        accepted_count=num_dates,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        request_id=request_id,
        trace_id=trace_id,
        request_payload=request.model_dump(mode="json"),
    )
    if not job_result.created:
        return build_batch_ack(
            message="Duplicate ingestion request accepted via idempotency replay.",
            entity_type="business_date",
            job_id=job_result.job.job_id,
            accepted_count=job_result.job.accepted_count,
            idempotency_key=idempotency_key,
        )
    logger.info(
        "Received request to ingest business dates.",
        extra={"num_dates": num_dates, "idempotency_key": idempotency_key},
    )

    try:
        await ingestion_service.publish_business_dates(
            request.business_dates, idempotency_key=idempotency_key
        )
    except IngestionPublishError as exc:
        await ingestion_job_service.mark_failed(
            job_result.job.job_id,
            str(exc),
            failed_record_keys=exc.failed_record_keys,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "INGESTION_PUBLISH_FAILED",
                "message": str(exc),
                "failed_record_keys": exc.failed_record_keys,
                "job_id": job_result.job.job_id,
            },
        ) from exc
    except Exception as exc:
        await ingestion_job_service.mark_failed(job_result.job.job_id, str(exc))
        raise

    try:
        await ingestion_job_service.mark_queued(job_result.job.job_id)
    except Exception as exc:
        await raise_post_publish_bookkeeping_failure(
            ingestion_job_service=ingestion_job_service,
            job_id=job_result.job.job_id,
            failure_reason=str(exc),
        )

    logger.info("Business dates successfully queued.", extra={"num_dates": num_dates})
    return build_batch_ack(
        message="Business dates accepted for asynchronous ingestion processing.",
        entity_type="business_date",
        job_id=job_result.job.job_id,
        accepted_count=num_dates,
        idempotency_key=idempotency_key,
    )
