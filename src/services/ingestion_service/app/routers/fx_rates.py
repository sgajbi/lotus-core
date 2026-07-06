# services/ingestion_service/app/routers/fx_rates.py
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..ack_response import build_batch_ack
from ..dependencies import get_ingestion_publish_command_handler
from ..DTOs.fx_rate_dto import FxRateIngestionRequest
from ..DTOs.ingestion_ack_dto import BatchIngestionAcceptedResponse
from ..request_metadata import resolve_idempotency_key
from ..services.ingestion_publish_commands import (
    BatchPublishIngestionCommand,
    IngestionPublishBookkeepingFailed,
    IngestionPublishCommandError,
    IngestionPublishCommandHandler,
    IngestionPublishUnavailable,
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
FX_RATE_PUBLISH_FAILED_EXAMPLE = ingestion_publish_failed_example(
    message="Failed to publish fx rate 'USD-SGD-2026-03-10'.",
    failed_record_keys=["USD-SGD-2026-03-10"],
    job_id="ing_01HZY3W6K8QF5B3Z7R9M2N1P0A",
)


@router.post(
    "/ingest/fx-rates",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    responses={
        status.HTTP_409_CONFLICT: ingestion_idempotency_conflict_response(),
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": "Write-rate protection blocked the FX-rate request.",
            "content": {"application/json": {"example": FX_RATE_RATE_LIMIT_EXCEEDED_EXAMPLE}},
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: ingestion_unavailable_response(
            mode_blocked_example=FX_RATE_MODE_BLOCKED_EXAMPLE,
            publish_failed_example=FX_RATE_PUBLISH_FAILED_EXAMPLE,
        ),
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
    command_handler: IngestionPublishCommandHandler = Depends(
        get_ingestion_publish_command_handler
    ),
):
    idempotency_key = resolve_idempotency_key(http_request)
    try:
        result = await command_handler.ingest_fx_rates(
            BatchPublishIngestionCommand(
                endpoint=str(http_request.url.path),
                entity_type="fx_rate",
                records=request.fx_rates,
                idempotency_key=idempotency_key,
                request_payload=request.model_dump(mode="json"),
                accepted_message="FX rates accepted for asynchronous ingestion processing.",
            ),
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
        logger.info("FX rates successfully queued.", extra={"num_rates": result.accepted_count})
    return build_batch_ack(
        message=result.message,
        entity_type=result.entity_type,
        job_id=result.job_id,
        accepted_count=result.accepted_count,
        idempotency_key=idempotency_key,
    )
