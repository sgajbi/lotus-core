# src/services/ingestion_service/app/routers/reprocessing.py
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from portfolio_common.kafka_utils import KafkaProducer, get_kafka_producer

from ..ack_response import build_batch_ack
from ..DTOs.ingestion_ack_dto import BatchIngestionAcceptedResponse
from ..DTOs.reprocessing_dto import ReprocessingRequest
from ..ops_controls import enforce_ingestion_write_rate_limit
from ..request_metadata import (
    create_ingestion_job_id,
    get_request_lineage,
    resolve_idempotency_key,
)
from ..services.ingestion_job_service import IngestionJobService, get_ingestion_job_service

logger = logging.getLogger(__name__)
router = APIRouter()

# Define the new topic name
REPROCESSING_REQUESTED_TOPIC = "transactions_reprocessing_requested"
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


@router.post(
    "/reprocess/transactions",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    responses={
        status.HTTP_409_CONFLICT: {
            "description": "Reprocessing publication is currently blocked by policy controls.",
            "content": {"application/json": {"example": REPROCESSING_BLOCKED_EXAMPLE}},
        },
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": "Write-rate protection blocked the reprocessing request.",
            "content": {
                "application/json": {"example": REPROCESSING_RATE_LIMIT_EXCEEDED_EXAMPLE}
            },
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "Ingestion operating mode blocked writes.",
            "content": {
                "application/json": {"example": REPROCESSING_MODE_BLOCKED_EXAMPLE}
            },
        },
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
    kafka_producer: KafkaProducer = Depends(get_kafka_producer),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    """
    Accepts a list of transaction IDs and publishes a reprocessing request
    event for each to a Kafka topic.
    """
    num_to_reprocess = len(request.transaction_ids)
    idempotency_key = resolve_idempotency_key(http_request)
    try:
        await ingestion_job_service.assert_ingestion_writable()
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "INGESTION_MODE_BLOCKS_WRITES", "message": str(exc)},
        ) from exc
    try:
        await ingestion_job_service.assert_reprocessing_publish_allowed(num_to_reprocess)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "INGESTION_REPLAY_BLOCKED", "message": str(exc)},
        ) from exc
    try:
        enforce_ingestion_write_rate_limit(
            endpoint="/reprocess/transactions",
            record_count=len(request.transaction_ids),
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "INGESTION_RATE_LIMIT_EXCEEDED", "message": str(exc)},
        ) from exc
    correlation_id, request_id, trace_id = get_request_lineage()
    job_id = create_ingestion_job_id()
    job_result = await ingestion_job_service.create_or_get_job(
        job_id=job_id,
        endpoint=str(http_request.url.path),
        entity_type="reprocessing_request",
        accepted_count=num_to_reprocess,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        request_id=request_id,
        trace_id=trace_id,
        request_payload=request.model_dump(mode="json"),
    )
    if not job_result.created:
        return build_batch_ack(
            message="Duplicate reprocessing request accepted via idempotency replay.",
            entity_type="reprocessing_request",
            job_id=job_result.job.job_id,
            accepted_count=job_result.job.accepted_count,
            idempotency_key=idempotency_key,
        )
    headers: list[tuple[str, bytes]] = []
    if correlation_id:
        headers.append(("correlation_id", correlation_id.encode("utf-8")))
    if idempotency_key:
        headers.append(("idempotency_key", idempotency_key.encode("utf-8")))

    logger.info(f"Received request to reprocess {num_to_reprocess} transaction(s).")

    try:
        for txn_id in request.transaction_ids:
            event_payload = {"transaction_id": txn_id}
            kafka_producer.publish_message(
                topic=REPROCESSING_REQUESTED_TOPIC,
                key=txn_id,  # Key by transaction_id for partitioning
                value=event_payload,
                headers=headers or None,
            )

        kafka_producer.flush(timeout=5)
        await ingestion_job_service.mark_queued(job_result.job.job_id)
    except Exception as exc:
        await ingestion_job_service.mark_failed(
            job_result.job.job_id,
            str(exc),
            failed_record_keys=request.transaction_ids,
        )
        raise

    logger.info(f"Successfully queued {num_to_reprocess} reprocessing requests.")
    return build_batch_ack(
        message=f"Successfully queued {num_to_reprocess} transactions for reprocessing.",
        entity_type="reprocessing_request",
        job_id=job_result.job.job_id,
        accepted_count=num_to_reprocess,
        idempotency_key=idempotency_key,
    )

