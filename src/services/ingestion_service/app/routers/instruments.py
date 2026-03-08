# services/ingestion_service/app/routers/instruments.py
import logging

from ..ack_response import build_batch_ack
from ..DTOs.ingestion_ack_dto import BatchIngestionAcceptedResponse
from ..DTOs.instrument_dto import InstrumentIngestionRequest
from ..ops_controls import enforce_ingestion_write_rate_limit
from ..request_metadata import (    create_ingestion_job_id,
    get_request_lineage,
    resolve_idempotency_key,
)
from ..services.ingestion_job_service import IngestionJobService, get_ingestion_job_service
from ..services.ingestion_service import (
    IngestionPublishError,
    IngestionService,
    get_ingestion_service,
)
from fastapi import APIRouter, Depends, HTTPException, Request, status

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/ingest/instruments",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    tags=["Instruments"],
    summary="Ingest instruments",
    description=(
        "What: Accept canonical instrument/security reference records.\n"
        "How: Validate schema, enforce ingestion mode/idempotency controls, and publish to asynchronous persistence pipeline.\n"
        "When: Use for security master onboarding and reference data corrections."
    ),
)
async def ingest_instruments(
    request: InstrumentIngestionRequest,
    http_request: Request,    ingestion_service: IngestionService = Depends(get_ingestion_service),
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
            endpoint="/ingest/instruments", record_count=len(request.instruments)
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "INGESTION_RATE_LIMIT_EXCEEDED", "message": str(exc)},
        ) from exc
    num_instruments = len(request.instruments)
    job_id = create_ingestion_job_id()
    correlation_id, request_id, trace_id = get_request_lineage()
    job_result = await ingestion_job_service.create_or_get_job(
        job_id=job_id,
        endpoint=str(http_request.url.path),
        entity_type="instrument",
        accepted_count=num_instruments,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        request_id=request_id,
        trace_id=trace_id,
        request_payload=request.model_dump(mode="json"),
    )
    if not job_result.created:
        return build_batch_ack(
            message="Duplicate ingestion request accepted via idempotency replay.",
            entity_type="instrument",
            job_id=job_result.job.job_id,
            accepted_count=job_result.job.accepted_count,
            idempotency_key=idempotency_key,
        )
    logger.info(
        "Received request to ingest instruments.",
        extra={"num_instruments": num_instruments, "idempotency_key": idempotency_key},
    )

    try:
        await ingestion_service.publish_instruments(
            request.instruments, idempotency_key=idempotency_key
        )
        await ingestion_job_service.mark_queued(job_result.job.job_id)
    except IngestionPublishError as exc:
        await ingestion_job_service.mark_failed(
            job_result.job.job_id,
            str(exc),
            failed_record_keys=exc.failed_record_keys,
        )
        raise
    except Exception as exc:
        await ingestion_job_service.mark_failed(job_result.job.job_id, str(exc))
        raise

    logger.info("Instruments successfully queued.", extra={"num_instruments": num_instruments})
    return build_batch_ack(
        message="Instruments accepted for asynchronous ingestion processing.",
        entity_type="instrument",
        job_id=job_result.job.job_id,
        accepted_count=num_instruments,
        idempotency_key=idempotency_key,
    )

