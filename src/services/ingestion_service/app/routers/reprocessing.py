# src/services/ingestion_service/app/routers/reprocessing.py
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from portfolio_common.logging_utils import operation_log_extra

from ..ack_response import build_batch_ack
from ..dependencies import (
    get_ingestion_job_service,  # noqa: F401
    get_ingestion_publish_command_handler,
)
from ..DTOs.ingestion_ack_dto import BatchIngestionAcceptedResponse
from ..DTOs.reprocessing_dto import ReprocessingRequest
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
    ingestion_conflict_response_with_idempotency_example,
    ingestion_publish_failed_example,
    ingestion_unavailable_response,
    raise_ingestion_publish_unavailable,
)

logger = logging.getLogger(__name__)
router = APIRouter()
REPROCESSING_BLOCKED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_REPLAY_BLOCKED",
        "message": "Reprocessing publication is temporarily blocked by operating policy.",
    }
}
REPROCESSING_MODE_BLOCKED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_MODE_BLOCKS_WRITES",
        "message": "Ingestion writes are currently disabled by operating mode.",
    }
}
REPROCESSING_RATE_LIMIT_EXCEEDED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_RATE_LIMIT_EXCEEDED",
        "message": "Ingestion write rate limit exceeded for /reprocess/transactions.",
    }
}
REPROCESSING_PUBLISH_FAILED_EXAMPLE = ingestion_publish_failed_example(
    message="Failed to publish reprocessing request 'TRN_002'.",
    failed_record_keys=["TRN_002", "TRN_003"],
    job_id="ing_01HZY3W6K8QF5B3Z7R9M2N1P0A",
)
REPROCESSING_SOURCE_NOT_FOUND_EXAMPLE = {
    "detail": {
        "code": "INGESTION_REPROCESSING_SOURCE_NOT_FOUND",
        "message": "One or more transactions are not available for reprocessing.",
        "missing_transaction_ids": ["TRN_404"],
    }
}
REPROCESSING_SOURCE_UNAVAILABLE_EXAMPLE = {
    "detail": {
        "code": "INGESTION_REPROCESSING_SOURCE_UNAVAILABLE",
        "message": "Transaction reprocessing source lookup is unavailable.",
    }
}


@router.post(
    "/reprocess/transactions",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    responses={
        status.HTTP_409_CONFLICT: ingestion_conflict_response_with_idempotency_example(
            description=(
                "Reprocessing publication is blocked by policy controls or the idempotency key "
                "was reused with a different canonical request payload."
            ),
            policy_blocked_example=REPROCESSING_BLOCKED_EXAMPLE,
        ),
        status.HTTP_404_NOT_FOUND: {
            "description": (
                "One or more requested transaction identifiers are absent from the "
                "authoritative Core transaction ledger."
            ),
            "content": {"application/json": {"example": REPROCESSING_SOURCE_NOT_FOUND_EXAMPLE}},
        },
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": "Write-rate protection blocked the reprocessing request.",
            "content": {"application/json": {"example": REPROCESSING_RATE_LIMIT_EXCEEDED_EXAMPLE}},
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: ingestion_unavailable_response(
            mode_blocked_example=REPROCESSING_MODE_BLOCKED_EXAMPLE,
            publish_failed_example=REPROCESSING_PUBLISH_FAILED_EXAMPLE,
            additional_examples={
                "source_unavailable": {
                    "summary": "Authoritative transaction source lookup failed.",
                    "value": REPROCESSING_SOURCE_UNAVAILABLE_EXAMPLE,
                }
            },
            description=(
                "Reprocessing is unavailable because operating mode blocks writes, the "
                "authoritative transaction source cannot be read, or Kafka publication failed."
            ),
        ),
    },
    tags=["Reprocessing"],
    summary="Request transaction reprocessing",
    description=(
        "What: Accept transaction identifiers that require deterministic historical "
        "recalculation.\n"
        "How: Validate request, persist ingestion job metadata, "
        "and publish reprocessing command events.\n"
        "When: Use for operational correction workflows after retroactive data changes."
    ),
)
async def reprocess_transactions(
    request: ReprocessingRequest,
    http_request: Request,
    command_handler: IngestionPublishCommandHandler = Depends(
        get_ingestion_publish_command_handler
    ),
):
    """
    Accepts a list of transaction IDs and publishes a reprocessing request
    event for each to a Kafka topic.
    """
    ordered_unique_transaction_ids = list(dict.fromkeys(request.transaction_ids))
    num_to_reprocess = len(ordered_unique_transaction_ids)
    idempotency_key = resolve_idempotency_key(http_request)
    try:
        result = await command_handler.ingest_reprocessing_requests(
            BatchPublishIngestionCommand(
                endpoint=str(http_request.url.path),
                entity_type="reprocessing_request",
                records=ordered_unique_transaction_ids,
                idempotency_key=idempotency_key,
                request_payload={"transaction_ids": ordered_unique_transaction_ids},
                accepted_message=(
                    f"Successfully queued {num_to_reprocess} transactions for reprocessing."
                ),
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
            "Transaction reprocessing requests queued.",
            extra=operation_log_extra(
                event_name="ingestion.reprocessing.requests_queued",
                operation="ingestion.reprocess_transactions",
                status="queued",
                reason_code="publish_queued",
                record_count=num_to_reprocess,
            ),
        )
    return build_batch_ack(
        message=result.message,
        entity_type=result.entity_type,
        job_id=result.job_id,
        accepted_count=result.accepted_count,
        idempotency_key=idempotency_key,
    )
