"""Resolve consumer section policy for governed Core snapshot requests."""

from __future__ import annotations

from dataclasses import dataclass

from ...contracts.core_snapshot import (
    CoreSnapshotPolicyProvenance,
    CoreSnapshotRequest,
    CoreSnapshotSection,
)


@dataclass
class SnapshotGovernanceContext:
    consumer_system: str
    tenant_id: str
    requested_sections: list[CoreSnapshotSection]
    applied_sections: list[CoreSnapshotSection]
    dropped_sections: list[CoreSnapshotSection]
    policy_version: str
    policy_source: str
    matched_rule_id: str
    strict_mode: bool
    warnings: list[str]


@dataclass(frozen=True)
class CoreSnapshotGovernanceResolution:
    requested_sections: list[CoreSnapshotSection]
    applied_sections: list[CoreSnapshotSection]
    dropped_sections: list[CoreSnapshotSection]
    policy_provenance: CoreSnapshotPolicyProvenance
    warnings: list[str]
    consumer_system: str
    tenant_id: str


def resolve_core_snapshot_governance(
    *,
    request: CoreSnapshotRequest,
    governance: SnapshotGovernanceContext | None,
) -> CoreSnapshotGovernanceResolution:
    if governance is not None:
        return CoreSnapshotGovernanceResolution(
            requested_sections=governance.requested_sections,
            applied_sections=governance.applied_sections,
            dropped_sections=governance.dropped_sections,
            policy_provenance=CoreSnapshotPolicyProvenance(
                policy_version=governance.policy_version,
                policy_source=governance.policy_source,
                matched_rule_id=governance.matched_rule_id,
                strict_mode=governance.strict_mode,
            ),
            warnings=governance.warnings,
            consumer_system=governance.consumer_system,
            tenant_id=governance.tenant_id,
        )

    return CoreSnapshotGovernanceResolution(
        requested_sections=list(request.sections),
        applied_sections=list(request.sections),
        dropped_sections=[],
        policy_provenance=CoreSnapshotPolicyProvenance(
            policy_version="snapshot.policy.inline.default",
            policy_source="snapshot.inline.default",
            matched_rule_id="snapshot.default",
            strict_mode=False,
        ),
        warnings=[],
        consumer_system=request.consumer_system,
        tenant_id=request.tenant_id,
    )
