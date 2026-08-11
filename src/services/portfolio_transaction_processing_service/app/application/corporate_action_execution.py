"""Bind corporate-action readiness to deterministic runtime execution authority."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from portfolio_common.domain.calculation_lineage import canonical_content_hash

from ..domain.transaction.corporate_action import (
    CorporateActionManifestFinding,
    CorporateActionManifestReadinessStatus,
)
from ..ports.corporate_action_event_graph import (
    CorporateActionChildObservation,
    CorporateActionReadinessDecision,
)


class CorporateActionExecutionDisposition(StrEnum):
    """Classify whether one durable readiness decision may execute financial effects."""

    PARKED = "PARKED"
    INVALID = "INVALID"
    READY = "READY"


@dataclass(frozen=True, slots=True)
class CorporateActionExecutionPlan:
    """Carry the exact structural and observation boundary for one release."""

    corporate_action_event_id: str
    portfolio_id: str
    linked_transaction_group_id: str
    parent_event_reference: str
    manifest_content_hash: str
    structural_plan_content_hash: str
    readiness_state_version: int
    through_observation_sequence: int
    ordered_transaction_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "corporate_action_event_id",
            "portfolio_id",
            "linked_transaction_group_id",
            "parent_event_reference",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
            object.__setattr__(self, field_name, value.strip())
        _require_sha256_digest(self.manifest_content_hash, "manifest_content_hash")
        _require_sha256_digest(
            self.structural_plan_content_hash,
            "structural_plan_content_hash",
        )
        if self.readiness_state_version < 1:
            raise ValueError("readiness_state_version must be positive")
        if self.through_observation_sequence < 0:
            raise ValueError("through_observation_sequence must be non-negative")
        if not self.ordered_transaction_ids:
            raise ValueError("ordered_transaction_ids must not be empty")
        normalized_ids = tuple(
            _required_text(transaction_id, "ordered_transaction_ids")
            for transaction_id in self.ordered_transaction_ids
        )
        if len(normalized_ids) != len(set(normalized_ids)):
            raise ValueError("ordered_transaction_ids must be unique")
        object.__setattr__(self, "ordered_transaction_ids", normalized_ids)

    @property
    def release_boundary_hash(self) -> str:
        """Bind event identity and observation boundary to the structural plan."""

        return cast(
            str,
            canonical_content_hash(
                {
                    "canonical_payload_version": 1,
                    "corporate_action_event_id": self.corporate_action_event_id,
                    "linked_transaction_group_id": self.linked_transaction_group_id,
                    "manifest_content_hash": self.manifest_content_hash,
                    "ordered_transaction_ids": list(self.ordered_transaction_ids),
                    "parent_event_reference": self.parent_event_reference,
                    "portfolio_id": self.portfolio_id,
                    "readiness_state_version": self.readiness_state_version,
                    "structural_plan_content_hash": self.structural_plan_content_hash,
                    "through_observation_sequence": self.through_observation_sequence,
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class CorporateActionExecutionGate:
    """Return a fail-closed execution disposition and optional authenticated plan."""

    disposition: CorporateActionExecutionDisposition
    readiness_status: CorporateActionManifestReadinessStatus
    findings: tuple[CorporateActionManifestFinding, ...]
    plan: CorporateActionExecutionPlan | None


def resolve_corporate_action_execution_gate(
    observation: CorporateActionChildObservation,
    decision: CorporateActionReadinessDecision,
) -> CorporateActionExecutionGate:
    """Permit execution only for a coherent READY decision with source-owned authority."""

    if decision.readiness_status is not CorporateActionManifestReadinessStatus.READY:
        if (
            decision.manifest_content_hash is not None
            or decision.structural_plan_content_hash is not None
            or decision.ordered_transaction_ids
        ):
            raise ValueError("non-ready corporate-action decision contains execution authority")
        return CorporateActionExecutionGate(
            disposition=(
                CorporateActionExecutionDisposition.INVALID
                if decision.readiness_status is CorporateActionManifestReadinessStatus.INVALID
                else CorporateActionExecutionDisposition.PARKED
            ),
            readiness_status=decision.readiness_status,
            findings=decision.findings,
            plan=None,
        )
    if decision.findings:
        raise ValueError("ready corporate-action decision contains blocking findings")
    if decision.manifest_content_hash is None:
        raise ValueError("ready corporate-action decision is missing manifest authority")
    if decision.structural_plan_content_hash is None:
        raise ValueError("ready corporate-action decision is missing structural-plan authority")
    return CorporateActionExecutionGate(
        disposition=CorporateActionExecutionDisposition.READY,
        readiness_status=decision.readiness_status,
        findings=(),
        plan=CorporateActionExecutionPlan(
            corporate_action_event_id=observation.corporate_action_event_id,
            portfolio_id=observation.portfolio_id,
            linked_transaction_group_id=observation.linked_transaction_group_id,
            parent_event_reference=observation.parent_event_reference,
            manifest_content_hash=decision.manifest_content_hash,
            structural_plan_content_hash=decision.structural_plan_content_hash,
            readiness_state_version=decision.state_version,
            through_observation_sequence=decision.through_observation_sequence,
            ordered_transaction_ids=decision.ordered_transaction_ids,
        ),
    )


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _require_sha256_digest(value: object, field_name: str) -> None:
    normalized = _required_text(value, field_name)
    if len(normalized) != 64 or normalized != normalized.lower():
        raise ValueError(f"{field_name} must be a canonical sha256 digest")
    try:
        int(normalized, 16)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a canonical sha256 digest") from exc
