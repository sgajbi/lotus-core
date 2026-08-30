# services/ingestion_service/app/routers/market_prices.py
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..ack_response import build_batch_ack
from ..application.reference_data_ingestion_registry import REFERENCE_DATA_INGESTION_REGISTRY
from ..dependencies import (
    get_ingestion_job_service,  # noqa: F401
    get_ingestion_publish_command_handler,
    get_reference_data_ingestion_command_handler,
)
from ..DTOs.ingestion_ack_dto import BatchIngestionAcceptedResponse
from ..DTOs.market_price_dto import (
    AuthoritativeMarketPriceSourceFactIngestionRequest,
    MarketPriceIngestionRequest,
)
from ..request_metadata import resolve_idempotency_key
from ..services.ingestion_publish_commands import (
    BatchPublishIngestionCommand,
    IngestionPublishBookkeepingFailed,
    IngestionPublishCommandError,
    IngestionPublishCommandHandler,
    IngestionPublishUnavailable,
)
from ..services.reference_data_ingestion_commands import (
    ReferenceDataBookkeepingFailed,
    ReferenceDataIngestionCommand,
    ReferenceDataIngestionCommandError,
    ReferenceDataIngestionCommandHandler,
)
from .job_bookkeeping import post_publish_bookkeeping_failure_detail
from .publish_errors import (
    ingestion_conflict_response_with_idempotency_example,
    ingestion_idempotency_conflict_response,
    ingestion_publish_failed_example,
    ingestion_unavailable_response,
    raise_ingestion_publish_unavailable,
)

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
MARKET_PRICE_PUBLISH_FAILED_EXAMPLE = ingestion_publish_failed_example(
    message="Failed to publish market price 'SEC_AAPL'.",
    failed_record_keys=["SEC_AAPL"],
    job_id="ing_01HZY3W6K8QF5B3Z7R9M2N1P0A",
)
MARKET_PRICE_SOURCE_FACT_CONFLICT_EXAMPLE = {
    "detail": {
        "code": "MARKET_PRICE_SOURCE_FACT_CONFLICT",
        "message": "multiple active market-price source records claim one exact authority",
        "job_id": "ing_01HZY3W6K8QF5B3Z7R9M2N1P0A",
    }
}
MARKET_PRICE_SOURCE_FACT_PERSIST_FAILED_EXAMPLE = {
    "detail": {
        "code": "REFERENCE_DATA_PERSIST_FAILED",
        "message": "Authoritative market-price source-fact persistence failed.",
        "job_id": "ing_01HZY3W6K8QF5B3Z7R9M2N1P0A",
    }
}


@router.post(
    "/ingest/market-prices",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    responses={
        status.HTTP_409_CONFLICT: ingestion_idempotency_conflict_response(),
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": "Write-rate protection blocked the market-price request.",
            "content": {"application/json": {"example": MARKET_PRICE_RATE_LIMIT_EXCEEDED_EXAMPLE}},
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: ingestion_unavailable_response(
            mode_blocked_example=MARKET_PRICE_MODE_BLOCKED_EXAMPLE,
            publish_failed_example=MARKET_PRICE_PUBLISH_FAILED_EXAMPLE,
        ),
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
    command_handler: IngestionPublishCommandHandler = Depends(
        get_ingestion_publish_command_handler
    ),
):
    idempotency_key = resolve_idempotency_key(http_request)
    try:
        result = await command_handler.ingest_market_prices(
            BatchPublishIngestionCommand(
                tenant_context=http_request.state.tenant_context,
                endpoint=str(http_request.url.path),
                entity_type="market_price",
                records=request.market_prices,
                idempotency_key=idempotency_key,
                request_payload=request.model_dump(mode="json"),
                accepted_message="Market prices accepted for asynchronous ingestion processing.",
            ),
        )
    except IngestionPublishCommandError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
            headers=exc.headers,
        ) from exc
    except IngestionPublishUnavailable as exc:
        raise_ingestion_publish_unavailable(exc.publish_error, job_id=exc.job_id)
    except IngestionPublishBookkeepingFailed as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=exc.detail,
        ) from exc

    if not result.replayed:
        logger.info(
            "Market prices successfully queued.",
            extra={"num_prices": result.accepted_count},
        )
    return build_batch_ack(
        message=result.message,
        entity_type=result.entity_type,
        job_id=result.job_id,
        accepted_count=result.accepted_count,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/ingest/authoritative-market-price-source-facts",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    responses={
        status.HTTP_409_CONFLICT: ingestion_conflict_response_with_idempotency_example(
            description=(
                "A source correction, authority overlap, or idempotency conflict blocked the write."
            ),
            policy_blocked_example=MARKET_PRICE_SOURCE_FACT_CONFLICT_EXAMPLE,
        ),
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": "Write-rate protection blocked the authoritative price request.",
            "content": {"application/json": {"example": MARKET_PRICE_RATE_LIMIT_EXCEEDED_EXAMPLE}},
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Persistence failed after ingestion job metadata was recorded.",
            "content": {
                "application/json": {"example": MARKET_PRICE_SOURCE_FACT_PERSIST_FAILED_EXAMPLE}
            },
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "Ingestion operating mode blocked writes.",
            "content": {"application/json": {"example": MARKET_PRICE_MODE_BLOCKED_EXAMPLE}},
        },
    },
    tags=["Market Prices"],
    summary="Ingest authoritative market-price source facts",
    description=(
        "What: Persist exact tenant, legal-book, instrument, business-date market-price "
        "authority with explicit quote representation and source lineage.\n"
        "How: Validate finite values and stable source-version identity, then serialize "
        "corrections and reject competing active authority before atomic append-only persistence.\n"
        "When: Use for valuation-policy execution that must distinguish unit price from clean "
        "or dirty percent-of-principal quotes. The legacy unscoped market-price projection is "
        "not modified or treated as authority by this endpoint. An idempotency key replays the "
        "same accepted request and rejects a different payload."
    ),
)
async def ingest_authoritative_market_price_source_facts(
    request: AuthoritativeMarketPriceSourceFactIngestionRequest,
    http_request: Request,
    command_handler: ReferenceDataIngestionCommandHandler = Depends(
        get_reference_data_ingestion_command_handler
    ),
) -> BatchIngestionAcceptedResponse:
    idempotency_key = resolve_idempotency_key(http_request)
    command = REFERENCE_DATA_INGESTION_REGISTRY.require("authoritative_market_price_source_fact")
    try:
        result = await command_handler.ingest_reference_data(
            ReferenceDataIngestionCommand(
                tenant_context=http_request.state.tenant_context,
                endpoint=str(http_request.url.path),
                idempotency_key=idempotency_key,
                registry_command=command,
                request=request,
            )
        )
    except ReferenceDataIngestionCommandError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except ReferenceDataBookkeepingFailed as exc:
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

    return build_batch_ack(
        message=result.message,
        entity_type=result.entity_type,
        job_id=result.job_id,
        accepted_count=result.accepted_count,
        idempotency_key=idempotency_key,
    )
