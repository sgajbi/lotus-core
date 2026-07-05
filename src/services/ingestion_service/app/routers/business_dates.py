# services/ingestion_service/app/routers/business_dates.py
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..ack_response import build_batch_ack
from ..dependencies import get_business_date_ingestion_policy, get_ingestion_service
from ..DTOs.business_date_dto import BusinessDateIngestionRequest
from ..DTOs.ingestion_ack_dto import BatchIngestionAcceptedResponse
from ..ops_controls import enforce_ingestion_write_rate_limit
from ..request_metadata import (
    create_ingestion_job_id,
    get_request_lineage,
    resolve_idempotency_key,
)
from ..services.business_date_ingestion_policy import (
    BusinessDateIngestionPolicy,
    BusinessDatePolicyViolation,
)
from ..services.ingestion_job_service import IngestionJobService, get_ingestion_job_service
from ..services.ingestion_service import (
    IngestionPublishError,
    IngestionService,
)
from .job_bookkeeping import mark_job_queued_after_publish_or_raise
from .publish_errors import (
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
    ingestion_service: IngestionService = Depends(get_ingestion_service),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
    business_date_policy: BusinessDateIngestionPolicy = Depends(get_business_date_ingestion_policy),
):
    idempotency_key = resolve_idempotency_key(http_request)
    await _assert_business_date_ingestion_writable(ingestion_job_service)
    _enforce_business_date_rate_limit(len(request.business_dates))
    await _validate_business_date_request(request, business_date_policy)

    num_dates = len(request.business_dates)
    job_result = await _create_business_date_ingestion_job(
        request=request,
        http_request=http_request,
        ingestion_job_service=ingestion_job_service,
        idempotency_key=idempotency_key,
        accepted_count=num_dates,
    )
    if not job_result.created:
        return _business_date_ack(
            message="Duplicate ingestion request accepted via idempotency replay.",
            job_id=job_result.job.job_id,
            accepted_count=job_result.job.accepted_count,
            idempotency_key=idempotency_key,
        )

    logger.info(
        "Received request to ingest business dates.",
        extra={"num_dates": num_dates, "idempotency_key": idempotency_key},
    )
    await _publish_business_dates_or_fail_job(
        request=request,
        ingestion_service=ingestion_service,
        ingestion_job_service=ingestion_job_service,
        job_id=job_result.job.job_id,
        idempotency_key=idempotency_key,
    )
    await _mark_business_date_job_queued(
        ingestion_job_service=ingestion_job_service,
        job_id=job_result.job.job_id,
        published_record_count=num_dates,
    )

    logger.info("Business dates successfully queued.", extra={"num_dates": num_dates})
    return _business_date_ack(
        message="Business dates accepted for asynchronous ingestion processing.",
        job_id=job_result.job.job_id,
        accepted_count=num_dates,
        idempotency_key=idempotency_key,
    )


async def _assert_business_date_ingestion_writable(
    ingestion_job_service: IngestionJobService,
) -> None:
    try:
        await ingestion_job_service.assert_ingestion_writable()
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "INGESTION_MODE_BLOCKS_WRITES", "message": str(exc)},
        ) from exc


def _enforce_business_date_rate_limit(record_count: int) -> None:
    try:
        enforce_ingestion_write_rate_limit(
            endpoint="/ingest/business-dates",
            record_count=record_count,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "INGESTION_RATE_LIMIT_EXCEEDED", "message": str(exc)},
        ) from exc


async def _validate_business_date_request(
    request: BusinessDateIngestionRequest,
    business_date_policy: BusinessDateIngestionPolicy,
) -> None:
    try:
        await business_date_policy.validate(request)
    except BusinessDatePolicyViolation as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


async def _create_business_date_ingestion_job(
    *,
    request: BusinessDateIngestionRequest,
    http_request: Request,
    ingestion_job_service: IngestionJobService,
    idempotency_key: str | None,
    accepted_count: int,
):
    correlation_id, request_id, trace_id = get_request_lineage()
    return await ingestion_job_service.create_or_get_job(
        job_id=create_ingestion_job_id(),
        endpoint=str(http_request.url.path),
        entity_type="business_date",
        accepted_count=accepted_count,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        request_id=request_id,
        trace_id=trace_id,
        request_payload=request.model_dump(mode="json"),
    )


async def _publish_business_dates_or_fail_job(
    *,
    request: BusinessDateIngestionRequest,
    ingestion_service: IngestionService,
    ingestion_job_service: IngestionJobService,
    job_id: str,
    idempotency_key: str | None,
) -> None:
    try:
        await ingestion_service.publish_business_dates(
            request.business_dates, idempotency_key=idempotency_key
        )
    except IngestionPublishError as exc:
        await ingestion_job_service.mark_failed(
            job_id,
            str(exc),
            failed_record_keys=exc.failed_record_keys,
        )
        raise_ingestion_publish_unavailable(exc, job_id=job_id)
    except Exception as exc:
        await ingestion_job_service.mark_failed(job_id, str(exc))
        raise


async def _mark_business_date_job_queued(
    *,
    ingestion_job_service: IngestionJobService,
    job_id: str,
    published_record_count: int,
) -> None:
    await mark_job_queued_after_publish_or_raise(
        ingestion_job_service=ingestion_job_service,
        job_id=job_id,
        published_record_count=published_record_count,
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
