"""Source-safe durable projection for ingestion failure evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SAFE_GENERIC_FAILURE_MESSAGE = (
    "Ingestion processing failed. Use the stable error code for recovery."
)

_SAFE_MESSAGES = {
    "INGESTION_PUBLISH_FAILED": ("Ingestion publishing failed before durable queue confirmation."),
    "INGESTION_JOB_BOOKKEEPING_FAILED": (
        "Ingestion work completed, but job bookkeeping did not complete afterward."
    ),
    "INGESTION_RETRY_PUBLISH_FAILED": (
        "Ingestion job retry could not be published to the downstream ingestion pipeline."
    ),
    "INGESTION_DLQ_REPLAY_FAILED": (
        "Consumer DLQ replay could not be published to the downstream ingestion pipeline."
    ),
    "INGESTION_RETRY_BOOKKEEPING_FAILED": (
        "Replay publish succeeded but post-publish bookkeeping did not complete."
    ),
    "INGESTION_DLQ_REPLAY_BOOKKEEPING_FAILED": (
        "Replay publish succeeded but post-publish bookkeeping did not complete."
    ),
    "MARKET_PRICE_SOURCE_FACT_CONFLICT": (
        "Authoritative market-price source evidence conflicts with persisted authority."
    ),
    "VALUATION_POLICY_ASSIGNMENT_CONFLICT": (
        "Valuation-policy assignment evidence conflicts with persisted authority."
    ),
    "REFERENCE_DATA_PERSIST_FAILED": "Reference-data persistence failed.",
}
_SAFE_DETAIL_KEYS = frozenset(
    {
        "dependency",
        "failed_record_keys",
        "job_id",
        "correlation_id",
        "request_id",
        "trace_id",
        "retryable",
        "retry_after_seconds",
        "publish_state",
        "published_record_count",
        "work_state",
        "retry_safe",
        "recovery_action",
        "recovery_path",
        "supportability_reason_code",
        "remediation",
    }
)
_MAX_TEXT_LENGTH = 512
_MAX_LIST_ITEMS = 100


@dataclass(frozen=True, slots=True)
class IngestionFailureEvidence:
    reason: str
    detail: dict[str, Any] | None
    headers: dict[str, str] | None


def project_ingestion_failure_evidence(
    *,
    failure_code: str | None,
    failure_detail: dict[str, Any] | None,
    failure_headers: dict[str, str] | None,
) -> IngestionFailureEvidence:
    """Remove arbitrary exception/client data while retaining bounded recovery evidence."""
    normalized_code = failure_code.strip() if failure_code is not None else None
    reason = _SAFE_MESSAGES.get(normalized_code, SAFE_GENERIC_FAILURE_MESSAGE)
    detail = _safe_detail(
        failure_code=normalized_code,
        safe_message=reason,
        failure_detail=failure_detail,
    )
    headers = _safe_headers(failure_headers)
    return IngestionFailureEvidence(reason=reason, detail=detail, headers=headers)


def _safe_detail(
    *,
    failure_code: str | None,
    safe_message: str,
    failure_detail: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if failure_code is None:
        return None
    projected: dict[str, Any] = {"code": failure_code, "message": safe_message}
    for key, value in (failure_detail or {}).items():
        if key not in _SAFE_DETAIL_KEYS:
            continue
        safe_value = _safe_value(value)
        if safe_value is not None:
            projected[key] = safe_value
    return projected


def _safe_value(value: Any) -> str | int | bool | list[str] | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, str):
        normalized = value.strip()
        return normalized[:_MAX_TEXT_LENGTH] if normalized else None
    if isinstance(value, list):
        projected = [
            normalized[:_MAX_TEXT_LENGTH]
            for item in value[:_MAX_LIST_ITEMS]
            if isinstance(item, str) and (normalized := item.strip())
        ]
        return projected
    return None


def _safe_headers(headers: dict[str, str] | None) -> dict[str, str] | None:
    if not headers:
        return None
    retry_after = next(
        (value for key, value in headers.items() if key.lower() == "retry-after"),
        None,
    )
    if retry_after is None:
        return None
    normalized = retry_after.strip()
    if not normalized.isdigit():
        return None
    return {"Retry-After": normalized}
