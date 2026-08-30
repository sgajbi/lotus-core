from __future__ import annotations

from typing import NoReturn

from fastapi import HTTPException, status

from ..application.ingestion_publish_outcome import (
    INGESTION_PUBLISH_DEPENDENCY,
    INGESTION_PUBLISH_FAILED_CODE,
    INGESTION_PUBLISH_RETRY_AFTER_SECONDS,
    build_ingestion_publish_failure_detail,
)
from ..request_metadata import get_request_lineage
from ..services.ingestion_service import IngestionPublishError

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
INGESTION_REQUEST_IN_PROGRESS_EXAMPLE = {
    "detail": {
        "code": "INGESTION_REQUEST_IN_PROGRESS",
        "message": "The original ingestion request has not reached a replay-safe state.",
        "job_id": "ing_01HZY3W6K8QF5B3Z7R9M2N1P0A",
        "status": "accepted",
    }
}
INGESTION_PORTFOLIO_TENANT_MISMATCH_EXAMPLE = {
    "detail": {
        "code": "INGESTION_PORTFOLIO_TENANT_MISMATCH",
        "message": (
            "Every transaction must reference a portfolio owned by the admitted tenant or "
            "introduced by the same admitted portfolio bundle."
        ),
    }
}


def ingestion_publish_failed_detail(
    exc: IngestionPublishError,
    *,
    job_id: str | None = None,
) -> dict[str, object]:
    correlation_id, request_id, trace_id = get_request_lineage()
    return build_ingestion_publish_failure_detail(
        message=str(exc),
        failed_record_keys=exc.failed_record_keys,
        published_record_count=exc.published_record_count,
        job_id=job_id,
        correlation_id=correlation_id,
        request_id=request_id,
        trace_id=trace_id,
    )


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
    additional_examples: dict[str, dict[str, object]] | None = None,
    description: str = (
        "Ingestion is unavailable because operating mode blocks writes or Kafka publish failed."
    ),
) -> dict[str, object]:
    examples: dict[str, dict[str, object]] = {
        "mode_blocked": {
            "summary": "Ingestion operating mode blocked writes.",
            "value": mode_blocked_example,
        },
        "publish_failed": {
            "summary": "Kafka publish dependency failed.",
            "value": publish_failed_example,
        },
    }
    if additional_examples:
        examples.update(additional_examples)
    return {
        "description": description,
        "headers": {
            "Retry-After": {
                "description": "Recommended retry delay in seconds for Kafka publish failures.",
                "schema": {"type": "integer", "minimum": 1},
            }
        },
        "content": {"application/json": {"examples": examples}},
    }


def ingestion_idempotency_conflict_response() -> dict[str, object]:
    return {
        "description": (
            "The idempotency key conflicts with another payload, or the matching request has "
            "not reached a replay-safe state."
        ),
        "content": {
            "application/json": {
                "examples": {
                    "idempotency_conflict": {
                        "summary": "Idempotency key payload conflict.",
                        "value": INGESTION_IDEMPOTENCY_CONFLICT_EXAMPLE,
                    },
                    "request_in_progress": {
                        "summary": "Matching request has not reached a replay-safe state.",
                        "value": INGESTION_REQUEST_IN_PROGRESS_EXAMPLE,
                    },
                }
            }
        },
    }


def ingestion_portfolio_tenant_mismatch_response() -> dict[str, object]:
    return {
        "description": (
            "A transaction or bundled portfolio does not belong to the admitted tenant scope."
        ),
        "content": {"application/json": {"example": INGESTION_PORTFOLIO_TENANT_MISMATCH_EXAMPLE}},
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
                    "request_in_progress": {
                        "summary": "Matching request has not reached a replay-safe state.",
                        "value": INGESTION_REQUEST_IN_PROGRESS_EXAMPLE,
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
