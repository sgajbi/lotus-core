# services/ingestion_service/app/routers/fx_rates.py
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..ack_response import build_batch_ack
from ..DTOs.fx_rate_dto import FxRateIngestionRequest
from ..DTOs.ingestion_ack_dto import BatchIngestionAcceptedResponse
from ..ops_controls import enforce_ingestion_write_rate_limit
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

FX_RATE_MODE_BLOCKED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_MODE_BLOCKS_WRITES",
        "message": "Ingestion writes are currently disabled by operating mode.",
    }
}
FX_RATE_RATE_LIMIT_EXCEEDED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_RATE_LIMIT_EXCEEDED",
        "message": "Ingestion write rate limit exceeded for /ingest/fx-rates.",
    }
}


@router.post(
    "/ingest/fx-rates",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    responses={
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": "Write-rate protection blocked the FX-rate request.",
            "content": {
                "application/json": {"example": FX_RATE_RATE_LIMIT_EXCEEDED_EXAMPLE}
            },
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "Ingestion operating mode blocked writes.",
            "content": {"application/json": {"example": FX_RATE_MODE_BLOCKED_EXAMPLE}},
        },
    },
    tags=["FX Rates"],
    summary="Ingest FX rates",
    description=(
        "What: Accept canonical foreign-exchange rate observations.\n"
        "How: Validate FX rate contract, enforce ingestion controls, and "
        "publish asynchronous events for downstream valuation.\n"
        "When: Use for scheduled FX reference updates and approved manual corrections."
    ),
)
async def ingest_fx_rates(
    request: FxRateIngestionRequest,
    http_request: Request,
    ingestion_service: IngestionService = Depends(get_ingestion_service),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
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
            endpoint="/ingest/fx-rates", record_count=len(request.fx_rates)
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "INGESTION_RATE_LIMIT_EXCEEDED", "message": str(exc)},
        ) from exc
    num_rates = len(request.fx_rates)
    job_id = create_ingestion_job_id()
    correlation_id, request_id, trace_id = get_request_lineage()
    job_result = await ingestion_job_service.create_or_get_job(
        job_id=job_id,
        endpoint=str(http_request.url.path),
        entity_type="fx_rate",
        accepted_count=num_rates,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        request_id=request_id,
        trace_id=trace_id,
        request_payload=request.model_dump(mode="json"),
    )
    if not job_result.created:
        return build_batch_ack(
            message="Duplicate ingestion request accepted via idempotency replay.",
            entity_type="fx_rate",
            job_id=job_result.job.job_id,
            accepted_count=job_result.job.accepted_count,
            idempotency_key=idempotency_key,
        )
    logger.info(
        "Received request to ingest fx rates.",
        extra={"num_rates": num_rates, "idempotency_key": idempotency_key},
    )

    try:
        await ingestion_service.publish_fx_rates(request.fx_rates, idempotency_key=idempotency_key)
    except IngestionPublishError as exc:
        await ingestion_job_service.mark_failed(
            job_result.job.job_id,
            str(exc),
            failed_record_keys=exc.failed_record_keys,
        )
        raise
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

    logger.info("FX rates successfully queued.", extra={"num_rates": num_rates})
    return build_batch_ack(
        message="FX rates accepted for asynchronous ingestion processing.",
        entity_type="fx_rate",
        job_id=job_result.job.job_id,
        accepted_count=num_rates,
        idempotency_key=idempotency_key,
    )

