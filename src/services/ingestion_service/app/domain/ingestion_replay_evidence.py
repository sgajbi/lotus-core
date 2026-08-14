"""Fail-closed authorization of durable ingestion payload replay evidence."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from .ingestion_evidence_policy import (
    INGESTION_EVIDENCE_POLICY_VERSION,
    DurablePayloadRepresentation,
)


class ReplayEvidenceFailure(StrEnum):
    POLICY_UNAVAILABLE = "policy_unavailable"
    POLICY_INELIGIBLE = "policy_ineligible"
    REPRESENTATION_UNAVAILABLE = "representation_unavailable"
    PAYLOAD_UNAVAILABLE = "payload_unavailable"
    EXPIRY_UNAVAILABLE = "expiry_unavailable"
    EXPIRED = "expired"


def replay_evidence_failure(
    context: Any,
    *,
    observed_at: datetime | None = None,
) -> ReplayEvidenceFailure | None:
    """Return why stored evidence cannot authorize replay, or ``None`` when valid."""
    if (
        getattr(context, "request_payload_policy_version", None)
        != INGESTION_EVIDENCE_POLICY_VERSION
    ):
        return ReplayEvidenceFailure.POLICY_UNAVAILABLE
    if getattr(context, "request_payload_replay_eligible", None) is not True:
        return ReplayEvidenceFailure.POLICY_INELIGIBLE
    if (
        getattr(context, "request_payload_representation", None)
        != DurablePayloadRepresentation.SOURCE_SAFE_REPLAY.value
    ):
        return ReplayEvidenceFailure.REPRESENTATION_UNAVAILABLE
    if not isinstance(getattr(context, "request_payload", None), dict):
        return ReplayEvidenceFailure.PAYLOAD_UNAVAILABLE
    expires_at = getattr(context, "request_payload_replay_expires_at", None)
    if not isinstance(expires_at, datetime) or expires_at.utcoffset() is None:
        return ReplayEvidenceFailure.EXPIRY_UNAVAILABLE
    now = observed_at or datetime.now(UTC)
    if now.utcoffset() is None:
        raise ValueError("Replay evidence observation time must be timezone-aware.")
    if now >= expires_at:
        return ReplayEvidenceFailure.EXPIRED
    return None
