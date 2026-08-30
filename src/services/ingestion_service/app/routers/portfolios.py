import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from portfolio_common.domain.tenant import TenantAuthorityMismatchError

from ..ack_response import build_batch_ack
from ..application.portfolio_tenant_authority import bind_portfolio_tenant_authority
from ..dependencies import (
    get_ingestion_job_service,  # noqa: F401
    get_ingestion_publish_command_handler,
)
from ..DTOs.ingestion_ack_dto import BatchIngestionAcceptedResponse
from ..DTOs.portfolio_dto import PortfolioIngestionRequest
from ..request_metadata import resolve_idempotency_key
from ..services.ingestion_publish_commands import (
    BatchPublishIngestionCommand,
    IngestionPublishBookkeepingFailed,
    IngestionPublishCommandError,
    IngestionPublishCommandHandler,
    IngestionPublishUnavailable,
)
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
    command_handler: IngestionPublishCommandHandler = Depends(
        get_ingestion_publish_command_handler
    ),
):
    idempotency_key = resolve_idempotency_key(http_request)
    try:
        bind_portfolio_tenant_authority(
            request.portfolios,
            http_request.state.tenant_context,
        )
    except TenantAuthorityMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="portfolio tenant scope must match the admitted tenant authority",
        ) from exc
    try:
        result = await command_handler.ingest_portfolios(
            BatchPublishIngestionCommand(
                tenant_context=http_request.state.tenant_context,
                endpoint=str(http_request.url.path),
                entity_type="portfolio",
                records=request.portfolios,
                idempotency_key=idempotency_key,
                request_payload=request.model_dump(mode="json"),
                accepted_message="Portfolios accepted for asynchronous ingestion processing.",
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
            "Portfolios successfully queued.", extra={"num_portfolios": result.accepted_count}
        )
    return build_batch_ack(
        message=result.message,
        entity_type=result.entity_type,
        job_id=result.job_id,
        accepted_count=result.accepted_count,
        idempotency_key=idempotency_key,
    )
