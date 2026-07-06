import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..ack_response import build_batch_ack
from ..dependencies import (
    get_ingestion_publish_command_handler,
    require_portfolio_bundle_adapter_enabled,
)
from ..DTOs.ingestion_ack_dto import BatchIngestionAcceptedResponse
from ..DTOs.portfolio_bundle_dto import PortfolioBundleIngestionRequest
from ..request_metadata import resolve_idempotency_key
from ..services.ingestion_publish_commands import (
    IngestionPublishBookkeepingFailed,
    IngestionPublishCommandError,
    IngestionPublishCommandHandler,
    IngestionPublishUnavailable,
    PortfolioBundlePublishIngestionCommand,
)
from .job_bookkeeping import post_publish_bookkeeping_failure_detail
from .publish_errors import (
    ingestion_idempotency_conflict_response,
    ingestion_publish_failed_example,
    ingestion_unavailable_response,
    raise_ingestion_publish_unavailable,
)

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
PORTFOLIO_BUNDLE_PUBLISH_FAILED_EXAMPLE = ingestion_publish_failed_example(
    message=(
        "Portfolio bundle publish stopped after these entity groups were already published: "
        "{'business_dates': 1, 'portfolios': 0, 'instruments': 0, "
        "'transactions': 0, 'market_prices': 0, 'fx_rates': 0}. "
        "Failed to publish portfolio 'P1'."
    ),
    failed_record_keys=["P1"],
    job_id="ing_01HZY3W6K8QF5B3Z7R9M2N1P0A",
    published_record_count=1,
)


@router.post(
    "/ingest/portfolio-bundle",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    responses={
        status.HTTP_409_CONFLICT: ingestion_idempotency_conflict_response(),
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
        status.HTTP_503_SERVICE_UNAVAILABLE: ingestion_unavailable_response(
            mode_blocked_example=PORTFOLIO_BUNDLE_MODE_BLOCKED_EXAMPLE,
            publish_failed_example=PORTFOLIO_BUNDLE_PUBLISH_FAILED_EXAMPLE,
        ),
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
    command_handler: IngestionPublishCommandHandler = Depends(
        get_ingestion_publish_command_handler
    ),
):
    idempotency_key = resolve_idempotency_key(http_request)
    accepted_count = (
        len(request.business_dates)
        + len(request.portfolios)
        + len(request.instruments)
        + len(request.transactions)
        + len(request.market_prices)
        + len(request.fx_rates)
    )
    try:
        result = await command_handler.ingest_portfolio_bundle(
            PortfolioBundlePublishIngestionCommand(
                endpoint=str(http_request.url.path),
                request=request,
                idempotency_key=idempotency_key,
                request_payload=request.model_dump(mode="json"),
                accepted_count=accepted_count,
            )
        )
    except IngestionPublishCommandError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except IngestionPublishUnavailable as exc:
        raise_ingestion_publish_unavailable(exc.publish_error, job_id=exc.job_id)
    except IngestionPublishBookkeepingFailed as exc:
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
            "Portfolio bundle queued for ingestion.",
            extra={
                "source_system": request.source_system,
                "mode": request.mode,
                "published_counts": (result.metadata or {}).get("published_counts", {}),
                "idempotency_key": idempotency_key,
            },
        )
    return build_batch_ack(
        message=result.message,
        entity_type=result.entity_type,
        job_id=result.job_id,
        accepted_count=result.accepted_count,
        idempotency_key=idempotency_key,
    )
