from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from portfolio_common.logging_utils import redact_sensitive

from ..domain.ingestion_evidence_policy import (
    INGESTION_EVIDENCE_POLICY_REGISTRY,
    DurablePayloadRepresentation,
)


@dataclass(frozen=True, slots=True)
class IngestionPayloadEvidence:
    request_payload: dict[str, Any] | None
    request_payload_fingerprint: str
    policy_version: str
    classification: str
    durable_representation: str
    replay_eligible: bool
    partial_replay_eligible: bool
    replay_expires_at: datetime | None
    retention_authority: str


def canonical_payload_text(payload: dict[str, Any] | None) -> str | None:
    if payload is None:
        return None
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def ingestion_payload_fingerprint(payload: dict[str, Any] | None) -> str | None:
    canonical = canonical_payload_text(payload)
    if canonical is None:
        return None
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def source_safe_request_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    return redact_sensitive(payload)


def source_safe_payload_fingerprint(payload: dict[str, Any] | None) -> str | None:
    return ingestion_payload_fingerprint(source_safe_request_payload(payload))


def build_ingestion_payload_evidence(
    *,
    endpoint: str,
    entity_type: str,
    payload: dict[str, Any],
    observed_at: datetime,
) -> IngestionPayloadEvidence:
    """Project a request into the only durable representation its policy permits."""
    if observed_at.utcoffset() is None:
        raise ValueError("Payload evidence observation time must be timezone-aware.")
    policy = INGESTION_EVIDENCE_POLICY_REGISTRY.require(endpoint, entity_type=entity_type)
    fingerprint = ingestion_payload_fingerprint(payload)
    if fingerprint is None:  # pragma: no cover - payload is non-optional by contract
        raise ValueError("Payload fingerprint is required.")
    replay_eligible = policy.replay_eligible
    if policy.durable_representation is DurablePayloadRepresentation.SOURCE_SAFE_REPLAY:
        durable_payload = source_safe_request_payload(payload)
        if policy.replay_ttl is None:  # guarded by policy construction
            raise ValueError("Replay policy is missing its technical expiry.")
        replay_expires_at = observed_at + policy.replay_ttl
    else:
        durable_payload = None
        replay_expires_at = None
    return IngestionPayloadEvidence(
        request_payload=durable_payload,
        request_payload_fingerprint=fingerprint,
        policy_version=policy.policy_version,
        classification=policy.classification.value,
        durable_representation=policy.durable_representation.value,
        replay_eligible=replay_eligible,
        partial_replay_eligible=policy.partial_replay_eligible,
        replay_expires_at=replay_expires_at,
        retention_authority=policy.retention_authority,
    )
