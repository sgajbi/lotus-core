from __future__ import annotations

import hmac
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from portfolio_common.logging_utils import redact_sensitive

from ..application.ingestion_evidence_hmac import purpose_bound_hmac_sha256_reference
from ..domain.ingestion_evidence_policy import (
    INGESTION_EVIDENCE_POLICY_REGISTRY,
    DurablePayloadRepresentation,
)

_FINGERPRINT_PATTERN = re.compile(
    r"^hmac-sha256:v1:(?P<key_id>[A-Za-z0-9][A-Za-z0-9._-]{0,63}):(?P<digest>[0-9a-f]{64})$"
)
_FINGERPRINT_DOMAIN = b"lotus-core/ingestion/request-payload-fingerprint/v1"


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


def ingestion_payload_fingerprint(
    payload: dict[str, Any] | None,
    *,
    key_id: str,
    hmac_secret: str,
) -> str | None:
    """Return a keyed, domain-separated fingerprint of the complete canonical request."""
    canonical = canonical_payload_text(payload)
    if canonical is None:
        return None
    if not key_id or not hmac_secret:
        raise ValueError("Payload fingerprint key id and HMAC secret are required.")
    return purpose_bound_hmac_sha256_reference(
        purpose=_FINGERPRINT_DOMAIN,
        value=canonical.encode("utf-8"),
        key_id=key_id,
        hmac_secret=hmac_secret,
    )


def ingestion_payload_fingerprint_matches(
    *,
    stored_fingerprint: str,
    payload: dict[str, Any] | None,
    secrets_by_key_id: Mapping[str, str],
) -> bool:
    """Verify a stored fingerprint using its declared active or retained rotation key."""
    match = _FINGERPRINT_PATTERN.fullmatch(stored_fingerprint)
    if match is None:
        return False
    key_id = match.group("key_id")
    secret = secrets_by_key_id.get(key_id)
    if secret is None:
        return False
    candidate = ingestion_payload_fingerprint(payload, key_id=key_id, hmac_secret=secret)
    return candidate is not None and hmac.compare_digest(stored_fingerprint, candidate)


def source_safe_request_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    return redact_sensitive(payload)


def build_ingestion_payload_evidence(
    *,
    endpoint: str,
    entity_type: str,
    payload: dict[str, Any],
    observed_at: datetime,
    fingerprint_key_id: str,
    fingerprint_hmac_secret: str,
) -> IngestionPayloadEvidence:
    """Project a request into the only durable representation its policy permits."""
    if observed_at.utcoffset() is None:
        raise ValueError("Payload evidence observation time must be timezone-aware.")
    policy = INGESTION_EVIDENCE_POLICY_REGISTRY.require(endpoint, entity_type=entity_type)
    fingerprint = ingestion_payload_fingerprint(
        payload,
        key_id=fingerprint_key_id,
        hmac_secret=fingerprint_hmac_secret,
    )
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
