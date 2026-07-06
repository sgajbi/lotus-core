# services/ingestion_service/app/routers/instruments.py
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..ack_response import build_batch_ack
from ..dependencies import (
    get_ingestion_job_service,  # noqa: F401
    get_ingestion_publish_command_handler,
)
from ..DTOs.ingestion_ack_dto import BatchIngestionAcceptedResponse
from ..DTOs.instrument_dto import InstrumentIngestionRequest
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

INSTRUMENT_MODE_BLOCKED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_MODE_BLOCKS_WRITES",
        "message": "Ingestion writes are currently disabled by operating mode.",
    }
}
INSTRUMENT_RATE_LIMIT_EXCEEDED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_RATE_LIMIT_EXCEEDED",
        "message": "Ingestion write rate limit exceeded for /ingest/instruments.",
    }
}
INSTRUMENT_PUBLISH_FAILED_EXAMPLE = ingestion_publish_failed_example(
    message="Failed to publish instrument 'SEC_BARC_PERP'.",
    failed_record_keys=["SEC_BARC_PERP"],
    job_id="ing_01HZY3W6K8QF5B3Z7R9M2N1P0A",
)


@router.post(
    "/ingest/instruments",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    responses={
        status.HTTP_409_CONFLICT: ingestion_idempotency_conflict_response(),
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": "Write-rate protection blocked the instrument request.",
            "content": {"application/json": {"example": INSTRUMENT_RATE_LIMIT_EXCEEDED_EXAMPLE}},
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: ingestion_unavailable_response(
            mode_blocked_example=INSTRUMENT_MODE_BLOCKED_EXAMPLE,
            publish_failed_example=INSTRUMENT_PUBLISH_FAILED_EXAMPLE,
        ),
    },
    tags=["Instruments"],
    summary="Ingest instruments",
    description=(
        "What: Accept canonical instrument/security reference records.\n"
        "How: Validate schema, enforce ingestion mode/idempotency controls, "
        "and publish to asynchronous persistence pipeline.\n"
        "When: Use for security master onboarding and reference data corrections."
    ),
)
async def ingest_instruments(
    request: InstrumentIngestionRequest,
    http_request: Request,
    command_handler: IngestionPublishCommandHandler = Depends(
        get_ingestion_publish_command_handler
    ),
):
    idempotency_key = resolve_idempotency_key(http_request)
    try:
        result = await command_handler.ingest_instruments(
            BatchPublishIngestionCommand(
                endpoint=str(http_request.url.path),
                entity_type="instrument",
                records=request.instruments,
                idempotency_key=idempotency_key,
                request_payload=request.model_dump(mode="json"),
                accepted_message="Instruments accepted for asynchronous ingestion processing.",
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
        logger.info(
            "Instruments successfully queued.",
            extra={"num_instruments": result.accepted_count},
        )
    return build_batch_ack(
        message=result.message,
        entity_type=result.entity_type,
        job_id=result.job_id,
        accepted_count=result.accepted_count,
        idempotency_key=idempotency_key,
    )
