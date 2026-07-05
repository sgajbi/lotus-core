from __future__ import annotations

from typing import NoReturn

from fastapi import HTTPException, status

from ..request_metadata import get_request_lineage
from ..services.ingestion_service import IngestionPublishError

INGESTION_PUBLISH_RETRY_AFTER_SECONDS = 30
INGESTION_PUBLISH_FAILED_CODE = "INGESTION_PUBLISH_FAILED"
INGESTION_PUBLISH_DEPENDENCY = "kafka"
INGESTION_IDEMPOTENCY_CONFLICT_EXAMPLE = {
    "detail": {
        "code": "INGESTION_IDEMPOTENCY_CONFLICT",
        "message": (
            "Ingestion idempotency key was reused for the same endpoint with a different payload."
        ),
        "endpoint": "/ingest/transactions",
        "idempotency_key": "ingestion-transactions-batch-20260301-001",
    }
}


def ingestion_publish_failed_detail(
    exc: IngestionPublishError,
    *,
    job_id: str | None = None,
) -> dict[str, object]:
    correlation_id, request_id, trace_id = get_request_lineage()
    published_record_count = exc.published_record_count
    detail: dict[str, object] = {
        "code": INGESTION_PUBLISH_FAILED_CODE,
        "message": str(exc),
        "dependency": INGESTION_PUBLISH_DEPENDENCY,
        "retryable": True,
        "retry_after_seconds": INGESTION_PUBLISH_RETRY_AFTER_SECONDS,
        "publish_state": "partial" if published_record_count else "unpublished",
        "published_record_count": published_record_count,
        "failed_record_keys": exc.failed_record_keys,
    }
    if job_id:
        detail["job_id"] = job_id
    if correlation_id:
        detail["correlation_id"] = correlation_id
    if request_id:
        detail["request_id"] = request_id
    if trace_id:
        detail["trace_id"] = trace_id
    return detail


def ingestion_publish_failed_example(
    *,
    message: str,
    failed_record_keys: list[str],
    job_id: str | None = None,
    published_record_count: int = 0,
    correlation_id: str = "corr_ingestion_publish_failed",
) -> dict[str, object]:
    detail: dict[str, object] = {
        "code": INGESTION_PUBLISH_FAILED_CODE,
        "message": message,
        "dependency": INGESTION_PUBLISH_DEPENDENCY,
        "retryable": True,
        "retry_after_seconds": INGESTION_PUBLISH_RETRY_AFTER_SECONDS,
        "publish_state": "partial" if published_record_count else "unpublished",
        "published_record_count": published_record_count,
        "failed_record_keys": failed_record_keys,
        "correlation_id": correlation_id,
    }
    if job_id:
        detail["job_id"] = job_id
    return {"detail": detail}


def ingestion_unavailable_response(
    *,
    mode_blocked_example: dict[str, object],
    publish_failed_example: dict[str, object],
    description: str = (
        "Ingestion is unavailable because operating mode blocks writes or Kafka publish failed."
    ),
) -> dict[str, object]:
    return {
        "description": description,
        "headers": {
            "Retry-After": {
                "description": "Recommended retry delay in seconds for Kafka publish failures.",
                "schema": {"type": "integer", "minimum": 1},
            }
        },
        "content": {
            "application/json": {
                "examples": {
                    "mode_blocked": {
                        "summary": "Ingestion operating mode blocked writes.",
                        "value": mode_blocked_example,
                    },
                    "publish_failed": {
                        "summary": "Kafka publish dependency failed.",
                        "value": publish_failed_example,
                    },
                }
            }
        },
    }


def ingestion_idempotency_conflict_response() -> dict[str, object]:
    return {
        "description": (
            "Idempotency key was reused for the same endpoint with a different canonical "
            "request payload."
        ),
        "content": {"application/json": {"example": INGESTION_IDEMPOTENCY_CONFLICT_EXAMPLE}},
    }


def ingestion_conflict_response_with_idempotency_example(
    *,
    description: str,
    policy_blocked_example: dict[str, object],
) -> dict[str, object]:
    return {
        "description": description,
        "content": {
            "application/json": {
                "examples": {
                    "policy_blocked": {
                        "summary": "Policy controls blocked the command.",
                        "value": policy_blocked_example,
                    },
                    "idempotency_conflict": {
                        "summary": "Idempotency key payload conflict.",
                        "value": INGESTION_IDEMPOTENCY_CONFLICT_EXAMPLE,
                    },
                }
            }
        },
    }


def raise_ingestion_publish_unavailable(
    exc: IngestionPublishError,
    *,
    job_id: str | None = None,
) -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=ingestion_publish_failed_detail(exc, job_id=job_id),
        headers={"Retry-After": str(INGESTION_PUBLISH_RETRY_AFTER_SECONDS)},
    ) from exc
