"""RFC-0083 ingestion evidence helpers for source lineage and partial outcomes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from portfolio_common.domain.tenant import TenantId

SOURCE_BATCH_ID_PREFIX = "srcbatch"
INGESTION_EVIDENCE_BUNDLE_ID_PREFIX = "ingev"

ACCEPTED = "accepted"
PARTIALLY_ACCEPTED = "partially_accepted"
REJECTED = "rejected"
QUARANTINED = "quarantined"
EMPTY = "empty"


@dataclass(frozen=True)
class SourceBatchIdentityScope:
    source_system: str
    source_batch_id: str
    payload_kind: str
    tenant_id: str
    feed_name: str | None = None
    observed_at: datetime | None = None
    ingested_at: datetime | None = None
    idempotency_key: str | None = None
    correlation_id: str | None = None
    source_record_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class IngestionOutcomeCounts:
    accepted_count: int = 0
    rejected_count: int = 0
    quarantined_count: int = 0


@dataclass(frozen=True)
class SourceBatchEvidence:
    source_system: str
    source_batch_id: str
    source_record_keys: tuple[str, ...]
    source_batch_fingerprint: str


@dataclass(frozen=True)
class IngestionEvidenceBundleIdentityScope:
    job_id: str
    endpoint: str
    entity_type: str
    accepted_count: int
    job_state: str
    request_payload_fingerprint: str | None = None
    failure_ids: tuple[str, ...] = ()
    replay_ids: tuple[str, ...] = ()
    consumer_dlq_event_ids: tuple[str, ...] = ()


def build_source_batch_fingerprint(scope: SourceBatchIdentityScope) -> str:
    """Build a stable fingerprint for the upstream source batch, not the ingestion attempt."""

    payload = _canonical_batch_payload(scope)
    digest = sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"{SOURCE_BATCH_ID_PREFIX}_{digest[:32]}"


def derive_source_batch_evidence(
    request_payload: dict[str, Any] | None,
    *,
    payload_kind: str,
) -> SourceBatchEvidence | None:
    """Derive source-owned batch evidence only from one unambiguous payload scope."""

    if request_payload is None:
        return None
    try:
        tenant_ids = {TenantId(value).value for value in _source_tenant_values(request_payload)}
    except (TypeError, ValueError):
        return None
    if len(tenant_ids) != 1:
        return None
    tenant_id = next(iter(tenant_ids))
    observations = tuple(_source_observations(request_payload))
    if not observations or any(
        observation["source_system"] is None or observation["source_batch_id"] is None
        for observation in observations
    ):
        return None
    batch_scopes = {
        (observation["source_system"], observation["source_batch_id"])
        for observation in observations
        if observation["source_system"] is not None and observation["source_batch_id"] is not None
    }
    if len(batch_scopes) != 1:
        return None
    source_system, source_batch_id = next(iter(batch_scopes))
    source_record_keys = tuple(
        sorted(
            {
                source_record_key
                for observation in observations
                if (source_record_key := observation["source_record_key"]) is not None
            }
        )
    )
    fingerprint = build_source_batch_fingerprint(
        SourceBatchIdentityScope(
            source_system=source_system,
            source_batch_id=source_batch_id,
            payload_kind=payload_kind,
            tenant_id=tenant_id,
            source_record_keys=source_record_keys,
        )
    )
    return SourceBatchEvidence(
        source_system=source_system,
        source_batch_id=source_batch_id,
        source_record_keys=source_record_keys,
        source_batch_fingerprint=fingerprint,
    )


def build_ingestion_evidence_bundle_id(
    scope: IngestionEvidenceBundleIdentityScope,
) -> str:
    """Build a stable identity for the exact durable evidence composition."""

    payload = {
        "consumer_dlq_event_ids": _canonical_identifiers(
            scope.consumer_dlq_event_ids,
            "consumer_dlq_event_ids",
        ),
        "accepted_count": _non_negative(scope.accepted_count, "accepted_count"),
        "endpoint": _clean_text(scope.endpoint, "endpoint"),
        "entity_type": _clean_text(scope.entity_type, "entity_type"),
        "failure_ids": _canonical_identifiers(scope.failure_ids, "failure_ids"),
        "job_id": _clean_text(scope.job_id, "job_id"),
        "job_state": _clean_text(scope.job_state, "job_state"),
        "request_payload_fingerprint": _optional_clean_text(scope.request_payload_fingerprint),
        "replay_ids": _canonical_identifiers(scope.replay_ids, "replay_ids"),
    }
    digest = sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"{INGESTION_EVIDENCE_BUNDLE_ID_PREFIX}_{digest[:32]}"


def classify_ingestion_outcome(counts: IngestionOutcomeCounts) -> str:
    _validate_ingestion_outcome_counts(counts)
    terminal_failures = _terminal_failure_count(counts)
    return _classify_valid_ingestion_outcome(
        accepted_count=counts.accepted_count,
        rejected_count=counts.rejected_count,
        quarantined_count=counts.quarantined_count,
        terminal_failures=terminal_failures,
    )


def _validate_ingestion_outcome_counts(counts: IngestionOutcomeCounts) -> None:
    _require_non_negative(counts.accepted_count, "accepted_count")
    _require_non_negative(counts.rejected_count, "rejected_count")
    _require_non_negative(counts.quarantined_count, "quarantined_count")


def _terminal_failure_count(counts: IngestionOutcomeCounts) -> int:
    return counts.rejected_count + counts.quarantined_count


def _classify_valid_ingestion_outcome(
    *,
    accepted_count: int,
    rejected_count: int,
    quarantined_count: int,
    terminal_failures: int,
) -> str:
    if _has_partial_ingestion_outcome(
        accepted_count=accepted_count,
        terminal_failures=terminal_failures,
    ):
        return PARTIALLY_ACCEPTED
    if accepted_count > 0:
        return ACCEPTED
    if quarantined_count > 0:
        return QUARANTINED
    if rejected_count > 0:
        return REJECTED
    return EMPTY


def _has_partial_ingestion_outcome(*, accepted_count: int, terminal_failures: int) -> bool:
    return accepted_count > 0 and terminal_failures > 0


def _canonical_batch_payload(scope: SourceBatchIdentityScope) -> dict[str, object]:
    source_system = _clean_text(scope.source_system, "source_system")
    source_batch_id = _clean_text(scope.source_batch_id, "source_batch_id")
    payload_kind = _clean_text(scope.payload_kind, "payload_kind")
    tenant_id = TenantId(scope.tenant_id).value
    feed_name = None
    if scope.feed_name is not None:
        feed_name = _clean_text(scope.feed_name, "feed_name")
    source_record_keys = [
        _clean_text(source_record_key, "source_record_keys")
        for source_record_key in scope.source_record_keys
    ]

    return {
        "feed_name": feed_name,
        "observed_at": _datetime_or_none(scope.observed_at),
        "payload_kind": payload_kind,
        "source_batch_id": source_batch_id,
        "source_record_keys": sorted(set(source_record_keys)),
        "source_system": source_system,
        "tenant_id": tenant_id,
    }


def _datetime_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime values must be timezone-aware")
    return value.astimezone(UTC).isoformat()


def _clean_text(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} is required")
    return cleaned


def _require_non_negative(value: int, field_name: str) -> None:
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _non_negative(value: int, field_name: str) -> int:
    _require_non_negative(value, field_name)
    return value


def _source_observations(value: Any):
    if isinstance(value, dict):
        source_system = _optional_clean_text(
            value.get("source_system") or value.get("source_vendor")
        )
        source_batch_id = _optional_clean_text(value.get("source_batch_id"))
        source_record_key = _optional_clean_text(
            value.get("source_record_id") or value.get("transaction_id") or value.get("record_key")
        )
        if source_system is not None or source_batch_id is not None:
            yield {
                "source_system": source_system,
                "source_batch_id": source_batch_id,
                "source_record_key": source_record_key,
            }
        for nested_value in value.values():
            yield from _source_observations(nested_value)
    elif isinstance(value, list):
        for nested_value in value:
            yield from _source_observations(nested_value)


def _source_tenant_values(value: Any):
    if isinstance(value, dict):
        if "tenant_id" in value:
            yield value["tenant_id"]
        for nested_value in value.values():
            yield from _source_tenant_values(nested_value)
    elif isinstance(value, list):
        for nested_value in value:
            yield from _source_tenant_values(nested_value)


def _optional_clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _canonical_identifiers(values: tuple[str, ...], field_name: str) -> list[str]:
    return sorted({_clean_text(value, field_name) for value in values})
