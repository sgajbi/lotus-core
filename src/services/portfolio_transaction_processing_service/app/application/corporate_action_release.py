"""Freeze full transaction authority for one ordered corporate-action release."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import cast

from portfolio_common.domain.calculation_lineage import canonical_content_hash

from ..domain import BookedTransaction, build_transaction_semantic_identity
from .corporate_action_execution import CorporateActionExecutionPlan


class CorporateActionReleaseMaterializationOutcome(StrEnum):
    """Classify an atomic release-ledger materialization attempt."""

    APPENDED = "APPENDED"
    UNCHANGED = "UNCHANGED"


@dataclass(frozen=True, slots=True)
class CorporateActionReleaseMaterialization:
    """Return durable identity for a materialized release generation."""

    outcome: CorporateActionReleaseMaterializationOutcome
    release_id: int
    release_authority_hash: str
    member_count: int


class StaleCorporateActionExecutionPlanError(ValueError):
    """Raised when READY authority is absent, stale, or inconsistent."""


class ConflictingCorporateActionExecutionReleaseError(ValueError):
    """Raised when persisted release evidence differs from deterministic authority."""


class LostCorporateActionExecutionLeaseError(ConflictingCorporateActionExecutionReleaseError):
    """Raised when a worker no longer owns the release fence it presented."""


class CorporateActionExecutionPayloadAuthorityError(
    ConflictingCorporateActionExecutionReleaseError
):
    """Raised when frozen member authority cannot be reconstructed exactly."""


class CorporateActionReleaseProgressOutcome(StrEnum):
    """Classify a fenced member-progress write."""

    ADVANCED = "ADVANCED"
    COMPLETE = "COMPLETE"
    LOST_OWNERSHIP = "LOST_OWNERSHIP"


@dataclass(frozen=True, slots=True, kw_only=True)
class CorporateActionExecutionLeaseRequest:
    """Request database-clock lease ownership for one release worker."""

    owner: str
    token: str
    duration_seconds: int

    def __post_init__(self) -> None:
        owner = _required_text(self.owner, "owner")
        if len(owner) > 128:
            raise ValueError("owner cannot exceed 128 characters")
        _require_sha256_digest(self.token, "token")
        if (
            isinstance(self.duration_seconds, bool)
            or not isinstance(self.duration_seconds, int)
            or not 1 <= self.duration_seconds <= 3600
        ):
            raise ValueError("duration_seconds must be between 1 and 3600")
        object.__setattr__(self, "owner", owner)


@dataclass(frozen=True, slots=True)
class ClaimedCorporateActionExecutionRelease:
    """Return the exact next member under monotonic fenced lease ownership."""

    release_id: int
    release_authority_hash: str
    member_count: int
    next_member: CorporateActionExecutionMemberAuthority
    attempt_count: int
    fence_token: int
    lease_owner: str
    lease_token: str
    lease_expires_at: datetime

    def __post_init__(self) -> None:
        _require_positive_integer(self.release_id, "release_id")
        _require_sha256_digest(self.release_authority_hash, "release_authority_hash")
        _require_positive_integer(self.member_count, "member_count")
        _require_positive_integer(self.attempt_count, "attempt_count")
        _require_positive_integer(self.fence_token, "fence_token")
        _required_text(self.lease_owner, "lease_owner")
        _require_sha256_digest(self.lease_token, "lease_token")
        if self.lease_expires_at.tzinfo is None or self.lease_expires_at.utcoffset() is None:
            raise ValueError("lease_expires_at must be timezone-aware")
        if self.next_member.execution_ordinal >= self.member_count:
            raise ValueError("next member ordinal must be within the release")


@dataclass(frozen=True, slots=True)
class CorporateActionExecutionMemberAuthority:
    """Bind one ordered member to observation and monetary transaction evidence."""

    execution_ordinal: int
    transaction_id: str
    observation_id: int
    transaction_epoch: int
    observed_child_content_hash: str
    transaction_payload_fingerprint: str

    def __post_init__(self) -> None:
        if self.execution_ordinal < 0:
            raise ValueError("execution_ordinal must be non-negative")
        _require_positive_integer(self.observation_id, "observation_id")
        if self.transaction_epoch < 0:
            raise ValueError("transaction_epoch must be non-negative")
        object.__setattr__(
            self,
            "transaction_id",
            _required_text(self.transaction_id, "transaction_id"),
        )
        _require_sha256_digest(
            self.observed_child_content_hash,
            "observed_child_content_hash",
        )
        _require_payload_fingerprint(self.transaction_payload_fingerprint)

    def lineage_payload(self) -> dict[str, object]:
        """Return the canonical member authority used by release hashing."""

        return {
            "execution_ordinal": self.execution_ordinal,
            "observation_id": self.observation_id,
            "observed_child_content_hash": self.observed_child_content_hash,
            "transaction_epoch": self.transaction_epoch,
            "transaction_id": self.transaction_id,
            "transaction_payload_fingerprint": self.transaction_payload_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class CorporateActionExecutionReleaseAuthority:
    """Carry the complete, deterministic authority for one release generation."""

    plan: CorporateActionExecutionPlan
    members: tuple[CorporateActionExecutionMemberAuthority, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.plan, CorporateActionExecutionPlan):
            raise TypeError("plan must be a CorporateActionExecutionPlan")
        if not self.members:
            raise ValueError("members must not be empty")
        ordered_ids = tuple(member.transaction_id for member in self.members)
        if ordered_ids != self.plan.ordered_transaction_ids:
            raise ValueError("members must match the exact structural execution order")
        if tuple(member.execution_ordinal for member in self.members) != tuple(
            range(len(self.members))
        ):
            raise ValueError("member execution ordinals must be contiguous from zero")
        observation_ids = tuple(member.observation_id for member in self.members)
        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError("member observation ids must be unique")

    @property
    def release_authority_hash(self) -> str:
        """Hash the boundary and frozen member evidence for replay-safe release."""

        return cast(
            str,
            canonical_content_hash(
                {
                    "canonical_payload_version": 1,
                    "members": [member.lineage_payload() for member in self.members],
                    "release_boundary_hash": self.plan.release_boundary_hash,
                }
            ),
        )


def build_corporate_action_execution_member_authority(
    *,
    execution_ordinal: int,
    observation_id: int,
    observed_child_content_hash: str,
    transaction_epoch: int,
    observed_transaction_payload_fingerprint: str,
    transaction: BookedTransaction,
) -> CorporateActionExecutionMemberAuthority:
    """Freeze one persisted transaction and reject observation/version drift."""

    if not isinstance(transaction, BookedTransaction):
        raise TypeError("transaction must be a BookedTransaction")
    persisted_epoch = transaction.epoch or 0
    if transaction_epoch != persisted_epoch:
        raise ValueError("observation epoch does not match the persisted transaction epoch")
    identity = build_transaction_semantic_identity(transaction)
    if identity.payload_fingerprint != observed_transaction_payload_fingerprint:
        raise ValueError("persisted transaction payload does not match observed source authority")
    return CorporateActionExecutionMemberAuthority(
        execution_ordinal=execution_ordinal,
        transaction_id=transaction.transaction_id,
        observation_id=observation_id,
        transaction_epoch=transaction_epoch,
        observed_child_content_hash=observed_child_content_hash,
        transaction_payload_fingerprint=observed_transaction_payload_fingerprint,
    )


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{field_name} must be canonical non-empty text")
    return value


def _require_positive_integer(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer")


def _require_sha256_digest(value: object, field_name: str) -> None:
    normalized = _required_text(value, field_name)
    if len(normalized) != 64 or normalized != normalized.lower():
        raise ValueError(f"{field_name} must be a canonical sha256 digest")
    try:
        int(normalized, 16)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a canonical sha256 digest") from exc


def _require_payload_fingerprint(value: object) -> None:
    normalized = _required_text(value, "transaction_payload_fingerprint")
    prefix, separator, digest = normalized.partition(":")
    if prefix != "sha256" or separator != ":":
        raise ValueError("transaction_payload_fingerprint must use sha256 authority")
    _require_sha256_digest(digest, "transaction_payload_fingerprint digest")
