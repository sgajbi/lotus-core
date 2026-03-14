import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..ack_response import build_batch_ack
from ..adapter_mode import require_portfolio_bundle_adapter_enabled
from ..DTOs.ingestion_ack_dto import BatchIngestionAcceptedResponse
from ..DTOs.portfolio_bundle_dto import PortfolioBundleIngestionRequest
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

PORTFOLIO_BUNDLE_DISABLED_EXAMPLE = {
    "detail": "Portfolio bundle adapter mode is disabled in this environment."
}
PORTFOLIO_BUNDLE_MODE_BLOCKED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_MODE_BLOCKS_WRITES",
        "message": "Ingestion writes are currently disabled by operating mode.",
    }
}
PORTFOLIO_BUNDLE_RATE_LIMIT_EXCEEDED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_RATE_LIMIT_EXCEEDED",
        "message": "Ingestion write rate limit exceeded for /ingest/portfolio-bundle.",
    }
}


@router.post(
    "/ingest/portfolio-bundle",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    responses={
        status.HTTP_410_GONE: {
            "description": "Portfolio bundle adapter mode disabled for this environment.",
            "content": {"application/json": {"example": PORTFOLIO_BUNDLE_DISABLED_EXAMPLE}},
        },
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": "Write-rate protection blocked the portfolio-bundle request.",
            "content": {
                "application/json": {"example": PORTFOLIO_BUNDLE_RATE_LIMIT_EXCEEDED_EXAMPLE}
            },
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "Ingestion operating mode blocked writes.",
            "content": {
                "application/json": {"example": PORTFOLIO_BUNDLE_MODE_BLOCKED_EXAMPLE}
            },
        },
    },
    tags=["Portfolio Bundle"],
    summary="Ingest a complete portfolio bundle",
    description=(
        "What: Accept a mixed onboarding bundle containing portfolio, instrument, transaction, "
        "market-price, FX-rate, and business-date records.\n"
        "How: Validate adapter payload and fan out records into existing canonical "
        "ingestion topics.\n"
        "When: Use for adapter-mode onboarding (UI/manual/file workflows), "
        "not primary upstream integration."
    ),
)
async def ingest_portfolio_bundle(
    request: PortfolioBundleIngestionRequest,
    http_request: Request,
    _: None = Depends(require_portfolio_bundle_adapter_enabled),
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
    accepted_count = (
        len(request.business_dates)
        + len(request.portfolios)
        + len(request.instruments)
        + len(request.transactions)
        + len(request.market_prices)
        + len(request.fx_rates)
    )
    try:
        enforce_ingestion_write_rate_limit(
            endpoint="/ingest/portfolio-bundle",
            record_count=accepted_count,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "INGESTION_RATE_LIMIT_EXCEEDED", "message": str(exc)},
        ) from exc
    job_id = create_ingestion_job_id()
    correlation_id, request_id, trace_id = get_request_lineage()
    job_result = await ingestion_job_service.create_or_get_job(
        job_id=job_id,
        endpoint=str(http_request.url.path),
        entity_type="portfolio_bundle",
        accepted_count=accepted_count,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        request_id=request_id,
        trace_id=trace_id,
        request_payload=request.model_dump(mode="json"),
    )
    if not job_result.created:
        return build_batch_ack(
            message="Duplicate ingestion request accepted via idempotency replay.",
            entity_type="portfolio_bundle",
            job_id=job_result.job.job_id,
            accepted_count=job_result.job.accepted_count,
            idempotency_key=idempotency_key,
        )
    try:
        published_counts = await ingestion_service.publish_portfolio_bundle(
            request, idempotency_key=idempotency_key
        )
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

    logger.info(
        "Portfolio bundle queued for ingestion.",
        extra={
            "source_system": request.source_system,
            "mode": request.mode,
            "published_counts": published_counts,
            "idempotency_key": idempotency_key,
        },
    )
    return build_batch_ack(
        message=(
            "Portfolio bundle accepted for asynchronous ingestion processing. "
            f"Published counts: {published_counts}"
        ),
        entity_type="portfolio_bundle",
        job_id=job_result.job.job_id,
        accepted_count=accepted_count,
        idempotency_key=idempotency_key,
    )

