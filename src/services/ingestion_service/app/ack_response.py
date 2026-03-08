from .DTOs.ingestion_ack_dto import BatchIngestionAcceptedResponse, IngestionAcceptedResponse
from .request_metadata import get_request_lineage


def build_single_ack(
    *,
    message: str,
    entity_type: str,
    idempotency_key: str | None,
) -> IngestionAcceptedResponse:
    correlation_id, request_id, trace_id = get_request_lineage()
    return IngestionAcceptedResponse(
        message=message,
        entity_type=entity_type,
        accepted_count=1,
        correlation_id=correlation_id,
        request_id=request_id,
        trace_id=trace_id,
        idempotency_key=idempotency_key,
    )


def build_batch_ack(
    *,
    message: str,
    entity_type: str,
    job_id: str,
    accepted_count: int,
    idempotency_key: str | None,
) -> BatchIngestionAcceptedResponse:
    correlation_id, request_id, trace_id = get_request_lineage()
    return BatchIngestionAcceptedResponse(
        message=message,
        entity_type=entity_type,
        accepted_count=accepted_count,
        job_id=job_id,
        correlation_id=correlation_id,
        request_id=request_id,
        trace_id=trace_id,
        idempotency_key=idempotency_key,
    )
