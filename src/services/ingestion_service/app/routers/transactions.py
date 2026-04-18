import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..ack_response import build_batch_ack, build_single_ack
from ..DTOs.ingestion_ack_dto import BatchIngestionAcceptedResponse, IngestionAcceptedResponse
from ..DTOs.transaction_dto import Transaction, TransactionIngestionRequest
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
TRANSACTION_PUBLISH_FAILED_EXAMPLE = {
    "detail": {
        "code": "INGESTION_PUBLISH_FAILED",
        "message": "Kafka publish failed for transaction payload.",
        "failed_record_keys": ["TRN_001"],
    }
}


@router.post(
    "/ingest/transaction",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=IngestionAcceptedResponse,
    responses={
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": "Write-rate protection blocked the single-transaction request.",
            "content": {"application/json": {"example": TRANSACTION_RATE_LIMIT_EXCEEDED_EXAMPLE}},
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Transaction publish failed after validation.",
            "content": {"application/json": {"example": TRANSACTION_PUBLISH_FAILED_EXAMPLE}},
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "Ingestion operating mode blocked writes.",
            "content": {"application/json": {"example": TRANSACTION_MODE_BLOCKED_EXAMPLE}},
        },
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
    ingestion_service: IngestionService = Depends(get_ingestion_service),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    idempotency_key = resolve_idempotency_key(request)
    try:
        await ingestion_job_service.assert_ingestion_writable()
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "INGESTION_MODE_BLOCKS_WRITES", "message": str(exc)},
        ) from exc
    try:
        enforce_ingestion_write_rate_limit(endpoint="/ingest/transaction", record_count=1)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "INGESTION_RATE_LIMIT_EXCEEDED", "message": str(exc)},
        ) from exc
    logger.info(
        "Received single transaction.",
        extra={
            "transaction_id": transaction.transaction_id,
            "portfolio_id": transaction.portfolio_id,
            "idempotency_key": idempotency_key,
        },
    )

    try:
        await ingestion_service.publish_transaction(transaction, idempotency_key=idempotency_key)
    except IngestionPublishError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "INGESTION_PUBLISH_FAILED",
                "message": str(exc),
                "failed_record_keys": exc.failed_record_keys,
            },
        ) from exc

    logger.info(
        "Transaction successfully queued.", extra={"transaction_id": transaction.transaction_id}
    )
    return build_single_ack(
        message="Transaction accepted for asynchronous ingestion processing.",
        entity_type="transaction",
        idempotency_key=idempotency_key,
    )


@router.post(
    "/ingest/transactions",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    responses={
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": "Write-rate protection blocked the transaction batch request.",
            "content": {
                "application/json": {"example": TRANSACTION_BATCH_RATE_LIMIT_EXCEEDED_EXAMPLE}
            },
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Transaction batch publish failed after job metadata was recorded.",
            "content": {"application/json": {"example": TRANSACTION_PUBLISH_FAILED_EXAMPLE}},
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "Ingestion operating mode blocked writes.",
            "content": {"application/json": {"example": TRANSACTION_MODE_BLOCKED_EXAMPLE}},
        },
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
            endpoint="/ingest/transactions", record_count=len(request.transactions)
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "INGESTION_RATE_LIMIT_EXCEEDED", "message": str(exc)},
        ) from exc
    num_transactions = len(request.transactions)
    job_id = create_ingestion_job_id()
    correlation_id, request_id, trace_id = get_request_lineage()
    job_result = await ingestion_job_service.create_or_get_job(
        job_id=job_id,
        endpoint=str(http_request.url.path),
        entity_type="transaction",
        accepted_count=num_transactions,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        request_id=request_id,
        trace_id=trace_id,
        request_payload=request.model_dump(mode="json"),
    )
    if not job_result.created:
        return build_batch_ack(
            message="Duplicate ingestion request accepted via idempotency replay.",
            entity_type="transaction",
            job_id=job_result.job.job_id,
            accepted_count=job_result.job.accepted_count,
            idempotency_key=idempotency_key,
        )
    logger.info(
        "Received request to ingest transactions.",
        extra={
            "num_transactions": num_transactions,
            "idempotency_key": idempotency_key,
            "job_id": job_id,
        },
    )

    try:
        await ingestion_service.publish_transactions(
            request.transactions, idempotency_key=idempotency_key
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

    logger.info("Transactions successfully queued.", extra={"num_transactions": num_transactions})
    return build_batch_ack(
        message="Transactions accepted for asynchronous ingestion processing.",
        entity_type="transaction",
        job_id=job_result.job.job_id,
        accepted_count=num_transactions,
        idempotency_key=idempotency_key,
    )
