# services/ingestion_service/app/routers/fx_rates.py
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from portfolio_common.fx_source_events import FxSourceCutSubmission

from ..ack_response import build_batch_ack
from ..dependencies import (
    get_ingestion_job_service,  # noqa: F401
    get_ingestion_publish_command_handler,
)
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
from .fx_source_submission import admit_fx_source_submission
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
        status.HTTP_403_FORBIDDEN: {
            "description": (
                "Canonical cuts require verified principal, enrollment and fixing calendar."
            ),
            "content": {
                "application/json": {
                    "example": {"detail": {"code": "FX_SOURCE_VERIFIED_PRINCIPAL_REQUIRED"}}
                }
            },
        },
        status.HTTP_413_CONTENT_TOO_LARGE: {
            "description": "The encoded canonical cut exceeds its bounded admission size.",
            "content": {
                "application/json": {
                    "example": {"detail": {"code": "FX_SOURCE_CUT_ENCODED_SIZE_EXCEEDED"}}
                }
            },
        },
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
        "What: Accept legacy FX rate batches or one complete fx.source-cut.v1 submission.\n"
        "How: Legacy batches retain their unqualified global projection behavior. Canonical cuts "
        "require a verified service principal and server-owned provider/source enrollment and "
        "fixing calendar, then publish one signed bounded command for atomic retained custody. "
        "A canonical acknowledgement counts one cut, not its members, and is not persistence "
        "completion or an unscoped valuation correction.\n"
        "When: Use for enrolled source fixings and predecessor-bound source corrections."
    ),
)
async def ingest_fx_rates(
    request: FxRateIngestionRequest | FxSourceCutSubmission,
    http_request: Request,
    command_handler: IngestionPublishCommandHandler = Depends(
        get_ingestion_publish_command_handler
    ),
):
    idempotency_key = resolve_idempotency_key(http_request)
    try:
        if isinstance(request, FxSourceCutSubmission):
            admitted = admit_fx_source_submission(request, http_request)
            result = await command_handler.ingest_fx_source_cut(
                BatchPublishIngestionCommand(
                    tenant_context=admitted.context,
                    endpoint=str(http_request.url.path),
                    entity_type="fx_source_cut",
                    records=(admitted.event,),
                    idempotency_key=idempotency_key,
                    request_payload=request.model_dump(mode="json"),
                    accepted_message=(
                        "One complete FX source cut accepted for asynchronous retention."
                    ),
                    admission_record_count=len(request.members),
                )
            )
        else:
            result = await command_handler.ingest_fx_rates(
                BatchPublishIngestionCommand(
                    tenant_context=http_request.state.tenant_context,
                    endpoint=str(http_request.url.path),
                    entity_type="fx_rate",
                    records=request.fx_rates,
                    idempotency_key=idempotency_key,
                    request_payload=request.model_dump(mode="json"),
                    accepted_message="FX rates accepted for asynchronous ingestion processing.",
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
            "FX ingestion successfully queued.",
            extra={"entity_type": result.entity_type, "accepted_count": result.accepted_count},
        )
    return build_batch_ack(
        message=result.message,
        entity_type=result.entity_type,
        job_id=result.job_id,
        accepted_count=result.accepted_count,
        idempotency_key=idempotency_key,
    )
