import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..ack_response import build_batch_ack
from ..dependencies import get_ingestion_service
from ..DTOs.ingestion_ack_dto import BatchIngestionAcceptedResponse
from ..DTOs.portfolio_dto import PortfolioIngestionRequest
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
)
from .job_bookkeeping import mark_job_queued_after_publish_or_raise
from .publish_errors import (
    ingestion_idempotency_conflict_response,
    ingestion_publish_failed_example,
    ingestion_unavailable_response,
    raise_ingestion_publish_unavailable,
)

logger = logging.getLogger(__name__)
router = APIRouter()

PORTFOLIO_MODE_BLOCKED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_MODE_BLOCKS_WRITES",
        "message": "Ingestion writes are currently disabled by operating mode.",
    }
}
PORTFOLIO_RATE_LIMIT_EXCEEDED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_RATE_LIMIT_EXCEEDED",
        "message": "Ingestion write rate limit exceeded for /ingest/portfolios.",
    }
}
PORTFOLIO_PUBLISH_FAILED_EXAMPLE = ingestion_publish_failed_example(
    message="Failed to publish portfolio 'P1'.",
    failed_record_keys=["P1"],
    job_id="ing_01HZY3W6K8QF5B3Z7R9M2N1P0A",
)


@router.post(
    "/ingest/portfolios",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    responses={
        status.HTTP_409_CONFLICT: ingestion_idempotency_conflict_response(),
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": "Write-rate protection blocked the portfolio request.",
            "content": {"application/json": {"example": PORTFOLIO_RATE_LIMIT_EXCEEDED_EXAMPLE}},
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: ingestion_unavailable_response(
            mode_blocked_example=PORTFOLIO_MODE_BLOCKED_EXAMPLE,
            publish_failed_example=PORTFOLIO_PUBLISH_FAILED_EXAMPLE,
        ),
    },
    tags=["Portfolios"],
    summary="Ingest portfolios",
    description=(
        "What: Accept canonical portfolio master records.\n"
        "How: Validate portfolio schema, enforce idempotency/mode checks, "
        "and publish asynchronously for persistence.\n"
        "When: Use when onboarding or updating portfolio metadata from upstream systems."
    ),
)
async def ingest_portfolios(
    request: PortfolioIngestionRequest,
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
            endpoint="/ingest/portfolios", record_count=len(request.portfolios)
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "INGESTION_RATE_LIMIT_EXCEEDED", "message": str(exc)},
        ) from exc
    num_portfolios = len(request.portfolios)
    job_id = create_ingestion_job_id()
    correlation_id, request_id, trace_id = get_request_lineage()
    job_result = await ingestion_job_service.create_or_get_job(
        job_id=job_id,
        endpoint=str(http_request.url.path),
        entity_type="portfolio",
        accepted_count=num_portfolios,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        request_id=request_id,
        trace_id=trace_id,
        request_payload=request.model_dump(mode="json"),
    )
    if not job_result.created:
        return build_batch_ack(
            message="Duplicate ingestion request accepted via idempotency replay.",
            entity_type="portfolio",
            job_id=job_result.job.job_id,
            accepted_count=job_result.job.accepted_count,
            idempotency_key=idempotency_key,
        )
    logger.info(
        "Received request to ingest portfolios.",
        extra={"num_portfolios": num_portfolios, "idempotency_key": idempotency_key},
    )

    try:
        await ingestion_service.publish_portfolios(
            request.portfolios, idempotency_key=idempotency_key
        )
    except IngestionPublishError as exc:
        await ingestion_job_service.mark_failed(
            job_result.job.job_id,
            str(exc),
            failed_record_keys=exc.failed_record_keys,
        )
        raise_ingestion_publish_unavailable(exc, job_id=job_result.job.job_id)
    except Exception as exc:
        await ingestion_job_service.mark_failed(job_result.job.job_id, str(exc))
        raise

    await mark_job_queued_after_publish_or_raise(
        ingestion_job_service=ingestion_job_service,
        job_id=job_result.job.job_id,
        published_record_count=num_portfolios,
    )

    logger.info("Portfolios successfully queued.", extra={"num_portfolios": num_portfolios})
    return build_batch_ack(
        message="Portfolios accepted for asynchronous ingestion processing.",
        entity_type="portfolio",
        job_id=job_result.job.job_id,
        accepted_count=num_portfolios,
        idempotency_key=idempotency_key,
    )
