import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..ack_response import build_batch_ack, build_single_ack
from ..dependencies import get_ingestion_publish_command_handler
from ..DTOs.ingestion_ack_dto import BatchIngestionAcceptedResponse, IngestionAcceptedResponse
from ..DTOs.transaction_dto import Transaction, TransactionIngestionRequest
from ..request_metadata import resolve_idempotency_key
from ..services.ingestion_publish_commands import (
    BatchPublishIngestionCommand,
    IngestionPublishBookkeepingFailed,
    IngestionPublishCommandError,
    IngestionPublishCommandHandler,
    IngestionPublishUnavailable,
    SinglePublishIngestionCommand,
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

TRANSACTION_MODE_BLOCKED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_MODE_BLOCKS_WRITES",
        "message": "Ingestion writes are currently disabled by operating mode.",
    }
}
TRANSACTION_RATE_LIMIT_EXCEEDED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_RATE_LIMIT_EXCEEDED",
        "message": "Ingestion write rate limit exceeded for /ingest/transaction.",
    }
}
TRANSACTION_BATCH_RATE_LIMIT_EXCEEDED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_RATE_LIMIT_EXCEEDED",
        "message": "Ingestion write rate limit exceeded for /ingest/transactions.",
    }
}
TRANSACTION_PUBLISH_FAILED_EXAMPLE = ingestion_publish_failed_example(
    message="Kafka publish failed for transaction payload.",
    failed_record_keys=["TRN_001"],
)


@router.post(
    "/ingest/transaction",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=IngestionAcceptedResponse,
    responses={
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": "Write-rate protection blocked the single-transaction request.",
            "content": {"application/json": {"example": TRANSACTION_RATE_LIMIT_EXCEEDED_EXAMPLE}},
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: ingestion_unavailable_response(
            mode_blocked_example=TRANSACTION_MODE_BLOCKED_EXAMPLE,
            publish_failed_example=TRANSACTION_PUBLISH_FAILED_EXAMPLE,
        ),
    },
    tags=["Transactions"],
    summary="Ingest a single transaction",
    description=(
        "What: Accept one canonical transaction record for ledger ingestion.\n"
        "How: Validate contract, enforce mode and rate controls, propagate any "
        "idempotency key as publish lineage, then publish asynchronously to Kafka.\n"
        "When: Use for low-volume operational corrections or single-record onboarding."
    ),
)
async def ingest_transaction(
    transaction: Transaction,
    request: Request,
    command_handler: IngestionPublishCommandHandler = Depends(
        get_ingestion_publish_command_handler
    ),
):
    idempotency_key = resolve_idempotency_key(request)
    try:
        result = await command_handler.ingest_transaction(
            SinglePublishIngestionCommand(
                endpoint=str(request.url.path),
                entity_type="transaction",
                record=transaction,
                idempotency_key=idempotency_key,
                accepted_message="Transaction accepted for asynchronous ingestion processing.",
            ),
        )
    except IngestionPublishCommandError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except IngestionPublishUnavailable as exc:
        raise_ingestion_publish_unavailable(exc.publish_error)

    logger.info(
        "Transaction successfully queued.", extra={"transaction_id": transaction.transaction_id}
    )
    return build_single_ack(
        message=result.message,
        entity_type=result.entity_type,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/ingest/transactions",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    responses={
        status.HTTP_409_CONFLICT: ingestion_idempotency_conflict_response(),
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": "Write-rate protection blocked the transaction batch request.",
            "content": {
                "application/json": {"example": TRANSACTION_BATCH_RATE_LIMIT_EXCEEDED_EXAMPLE}
            },
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: ingestion_unavailable_response(
            mode_blocked_example=TRANSACTION_MODE_BLOCKED_EXAMPLE,
            publish_failed_example=TRANSACTION_PUBLISH_FAILED_EXAMPLE,
        ),
    },
    tags=["Transactions"],
    summary="Ingest a transaction batch",
    description=(
        "What: Accept a batch of canonical transaction records.\n"
        "How: Persist ingestion job metadata, validate payload, and publish "
        "all valid records asynchronously.\n"
        "When: Use for standard API-driven batch ingestion workflows."
    ),
)
async def ingest_transactions(
    request: TransactionIngestionRequest,
    http_request: Request,
    command_handler: IngestionPublishCommandHandler = Depends(
        get_ingestion_publish_command_handler
    ),
):
    idempotency_key = resolve_idempotency_key(http_request)
    try:
        result = await command_handler.ingest_transactions(
            BatchPublishIngestionCommand(
                endpoint=str(http_request.url.path),
                entity_type="transaction",
                records=request.transactions,
                idempotency_key=idempotency_key,
                request_payload=request.model_dump(mode="json"),
                accepted_message="Transactions accepted for asynchronous ingestion processing.",
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
            "Transactions successfully queued.",
            extra={"num_transactions": result.accepted_count},
        )
    return build_batch_ack(
        message=result.message,
        entity_type=result.entity_type,
        job_id=result.job_id,
        accepted_count=result.accepted_count,
        idempotency_key=idempotency_key,
    )
