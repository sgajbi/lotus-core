"""Validated effective-dated replay identity and sibling-merge policy."""

from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Any, cast

from .reprocessing_payload_integrity import (
    PendingReplaySiblingEvidence,
    effective_dated_replay_identity_key,
    replay_text_is_storage_safe,
)

EARLIEST_IMPACTED_DATE_JOB_TYPES = frozenset({"RESET_WATERMARKS", "RESET_FX_WATERMARKS"})


@dataclass(frozen=True, slots=True)
class EffectiveDatedReplayIdentity:
    """Validated identity needed to serialize one effective-dated replay family."""

    job_type: str
    identity_key: str
    payload: dict[str, Any]
    generated_at: datetime | None
    attempt_count: int
    correlation_id: str | None
    correlation_missing_reason: str | None
    alternate_lookup_key: str | None


def validated_effective_dated_replay_identity(
    *,
    job_type: str,
    payload: Any,
    attempt_count: int,
    correlation_id: str | None,
    correlation_missing_reason: str | None,
    alternate_lookup_key: str | None,
) -> EffectiveDatedReplayIdentity:
    if job_type not in EARLIEST_IMPACTED_DATE_JOB_TYPES or not isinstance(payload, dict):
        raise ValueError("owned requeue requires a supported effective-dated replay payload")
    earliest_impacted_date = required_replay_payload_text(payload, "earliest_impacted_date")
    date.fromisoformat(earliest_impacted_date)
    components: tuple[str, ...]
    generated_at: datetime | None = None
    if job_type == "RESET_WATERMARKS":
        components = (required_replay_payload_text(payload, "security_id"),)
    else:
        components = (
            required_replay_payload_text(payload, "from_currency"),
            required_replay_payload_text(payload, "to_currency"),
        )
        required_replay_payload_text(payload, "content_hash")
        generated_at = datetime.fromisoformat(required_replay_payload_text(payload, "generated_at"))
        if generated_at.tzinfo is None or generated_at.utcoffset() is None:
            raise ValueError("FX replay generated_at must be timezone-aware")
    return EffectiveDatedReplayIdentity(
        job_type=job_type,
        identity_key=effective_dated_replay_identity_key(job_type, *components),
        payload=cast(dict[str, Any], payload),
        generated_at=generated_at,
        attempt_count=attempt_count,
        correlation_id=correlation_id,
        correlation_missing_reason=correlation_missing_reason,
        alternate_lookup_key=alternate_lookup_key,
    )


def merge_replay_sibling_evidence(
    identity: EffectiveDatedReplayIdentity,
    evidence: PendingReplaySiblingEvidence,
) -> EffectiveDatedReplayIdentity:
    """Merge locked retry, boundary, and source truth without changing sibling ownership."""

    owned_boundary = date.fromisoformat(identity.payload["earliest_impacted_date"])
    earliest_sibling = evidence.earliest_sibling
    earliest_boundary = min(
        owned_boundary,
        (
            cast(date, earliest_sibling.earliest_impacted_date)
            if earliest_sibling is not None
            else date.max
        ),
    )
    source = identity
    if identity.job_type == "RESET_WATERMARKS":
        boundary_siblings = [
            sibling
            for sibling in evidence.siblings
            if sibling.earliest_impacted_date == earliest_boundary
        ]
        lineage_sibling = next(
            (sibling for sibling in boundary_siblings if sibling.correlation_id is not None),
            None,
        )
        if (
            lineage_sibling is None
            and earliest_boundary < owned_boundary
            and identity.correlation_id is None
        ):
            lineage_sibling = earliest_sibling
        if lineage_sibling is not None and (
            earliest_boundary < owned_boundary or identity.correlation_id is None
        ):
            source = replace(
                identity,
                correlation_id=lineage_sibling.correlation_id,
                correlation_missing_reason=lineage_sibling.correlation_missing_reason,
                alternate_lookup_key=lineage_sibling.alternate_lookup_key,
            )
    elif identity.job_type == "RESET_FX_WATERMARKS":
        source = _latest_valid_fx_source(identity, evidence)

    payload = {**source.payload, "earliest_impacted_date": earliest_boundary.isoformat()}
    return replace(
        source,
        payload=payload,
        attempt_count=max(identity.attempt_count, evidence.max_attempt_count),
    )


def _latest_valid_fx_source(
    identity: EffectiveDatedReplayIdentity,
    evidence: PendingReplaySiblingEvidence,
) -> EffectiveDatedReplayIdentity:
    source = identity
    for sibling in evidence.siblings:
        try:
            candidate = validated_effective_dated_replay_identity(
                job_type=identity.job_type,
                payload=sibling.payload,
                attempt_count=sibling.attempt_count,
                correlation_id=sibling.correlation_id,
                correlation_missing_reason=sibling.correlation_missing_reason,
                alternate_lookup_key=sibling.alternate_lookup_key,
            )
        except (TypeError, ValueError):
            continue
        if _fx_source_key(candidate) > _fx_source_key(source):
            source = candidate
    return source


def _fx_source_key(identity: EffectiveDatedReplayIdentity) -> tuple[datetime, str]:
    return cast(datetime, identity.generated_at), identity.payload["content_hash"]


def required_replay_payload_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"effective-dated replay payload requires {key}")
    if value != value.strip():
        raise ValueError(f"effective-dated replay payload {key} must be normalized")
    if not replay_text_is_storage_safe(value):
        raise ValueError(f"effective-dated replay payload {key} is not storage-safe text")
    return value


def parse_replay_earliest_date(payload: object) -> date | None:
    try:
        if not isinstance(payload, dict):
            return None
        return date.fromisoformat(required_replay_payload_text(payload, "earliest_impacted_date"))
    except (TypeError, ValueError):
        return None
