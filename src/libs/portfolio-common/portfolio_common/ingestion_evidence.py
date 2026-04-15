"""RFC-0083 ingestion evidence helpers for source lineage and partial outcomes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256


SOURCE_BATCH_ID_PREFIX = "srcbatch"

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
    tenant_id: str = "default"
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


def build_source_batch_fingerprint(scope: SourceBatchIdentityScope) -> str:
    """Build a stable fingerprint for the upstream source batch, not the ingestion attempt."""

    payload = _canonical_batch_payload(scope)
    digest = sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"{SOURCE_BATCH_ID_PREFIX}_{digest[:32]}"


def classify_ingestion_outcome(counts: IngestionOutcomeCounts) -> str:
    _require_non_negative(counts.accepted_count, "accepted_count")
    _require_non_negative(counts.rejected_count, "rejected_count")
    _require_non_negative(counts.quarantined_count, "quarantined_count")

    terminal_failures = counts.rejected_count + counts.quarantined_count
    if counts.accepted_count > 0 and terminal_failures > 0:
        return PARTIALLY_ACCEPTED
    if counts.accepted_count > 0:
        return ACCEPTED
    if counts.quarantined_count > 0:
        return QUARANTINED
    if counts.rejected_count > 0:
        return REJECTED
    return EMPTY


def _canonical_batch_payload(scope: SourceBatchIdentityScope) -> dict[str, object]:
    source_system = _clean_text(scope.source_system, "source_system")
    source_batch_id = _clean_text(scope.source_batch_id, "source_batch_id")
    payload_kind = _clean_text(scope.payload_kind, "payload_kind")
    tenant_id = _clean_text(scope.tenant_id, "tenant_id")
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
