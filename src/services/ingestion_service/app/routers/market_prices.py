# services/ingestion_service/app/routers/market_prices.py
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..ack_response import build_batch_ack
from ..DTOs.ingestion_ack_dto import BatchIngestionAcceptedResponse
from ..DTOs.market_price_dto import MarketPriceIngestionRequest
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

MARKET_PRICE_MODE_BLOCKED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_MODE_BLOCKS_WRITES",
        "message": "Ingestion writes are currently disabled by operating mode.",
    }
}
MARKET_PRICE_RATE_LIMIT_EXCEEDED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_RATE_LIMIT_EXCEEDED",
        "message": "Ingestion write rate limit exceeded for /ingest/market-prices.",
    }
}
MARKET_PRICE_PUBLISH_FAILED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_PUBLISH_FAILED",
        "message": "Failed to publish market price 'SEC_AAPL'.",
        "failed_record_keys": ["SEC_AAPL"],
        "job_id": "ing_01HZY3W6K8QF5B3Z7R9M2N1P0A",
    }
}


@router.post(
    "/ingest/market-prices",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    responses={
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": "Write-rate protection blocked the market-price request.",
            "content": {"application/json": {"example": MARKET_PRICE_RATE_LIMIT_EXCEEDED_EXAMPLE}},
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Market-price publish failed after job metadata was recorded.",
            "content": {"application/json": {"example": MARKET_PRICE_PUBLISH_FAILED_EXAMPLE}},
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "Ingestion operating mode blocked writes.",
            "content": {"application/json": {"example": MARKET_PRICE_MODE_BLOCKED_EXAMPLE}},
        },
    },
    tags=["Market Prices"],
    summary="Ingest market prices",
    description=(
        "What: Accept canonical market price observations for securities.\n"
        "How: Validate payload, enforce ingestion guardrails, and publish "
        "asynchronous events for valuation processing.\n"
        "When: Use for daily close pricing loads or intraday approved market data updates."
    ),
)
async def ingest_market_prices(
    request: MarketPriceIngestionRequest,
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
            endpoint="/ingest/market-prices", record_count=len(request.market_prices)
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "INGESTION_RATE_LIMIT_EXCEEDED", "message": str(exc)},
        ) from exc
    num_prices = len(request.market_prices)
    job_id = create_ingestion_job_id()
    correlation_id, request_id, trace_id = get_request_lineage()
    job_result = await ingestion_job_service.create_or_get_job(
        job_id=job_id,
        endpoint=str(http_request.url.path),
        entity_type="market_price",
        accepted_count=num_prices,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        request_id=request_id,
        trace_id=trace_id,
        request_payload=request.model_dump(mode="json"),
    )
    if not job_result.created:
        return build_batch_ack(
            message="Duplicate ingestion request accepted via idempotency replay.",
            entity_type="market_price",
            job_id=job_result.job.job_id,
            accepted_count=job_result.job.accepted_count,
            idempotency_key=idempotency_key,
        )
    logger.info(
        "Received request to ingest market prices.",
        extra={"num_prices": num_prices, "idempotency_key": idempotency_key},
    )

    try:
        await ingestion_service.publish_market_prices(
            request.market_prices, idempotency_key=idempotency_key
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

    logger.info("Market prices successfully queued.", extra={"num_prices": num_prices})
    return build_batch_ack(
        message="Market prices accepted for asynchronous ingestion processing.",
        entity_type="market_price",
        job_id=job_result.job.job_id,
        accepted_count=num_prices,
        idempotency_key=idempotency_key,
    )
