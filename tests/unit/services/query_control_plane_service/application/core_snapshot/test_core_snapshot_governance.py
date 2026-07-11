from datetime import date

from src.services.query_control_plane_service.app.application.core_snapshot.governance import (
    SnapshotGovernanceContext,
    resolve_core_snapshot_governance,
)
from src.services.query_control_plane_service.app.contracts.core_snapshot import (
    CoreSnapshotRequest,
    CoreSnapshotSection,
)


def test_core_snapshot_governance_defaults_to_requested_sections() -> None:
    request = CoreSnapshotRequest(
        as_of_date=date(2026, 4, 10),
        sections=[
            CoreSnapshotSection.PORTFOLIO_STATE,
            CoreSnapshotSection.PORTFOLIO_TOTALS,
        ],
        consumer_system="lotus-idea",
        tenant_id="tenant-sg",
    )

    resolution = resolve_core_snapshot_governance(request=request, governance=None)

    assert resolution.consumer_system == "lotus-idea"
    assert resolution.tenant_id == "tenant-sg"
    assert resolution.requested_sections == [
        CoreSnapshotSection.PORTFOLIO_STATE,
        CoreSnapshotSection.PORTFOLIO_TOTALS,
    ]
    assert resolution.applied_sections == resolution.requested_sections
    assert resolution.dropped_sections == []
    assert resolution.warnings == []
    assert resolution.policy_provenance.policy_version == "snapshot.policy.inline.default"
    assert resolution.policy_provenance.policy_source == "snapshot.inline.default"
    assert resolution.policy_provenance.matched_rule_id == "snapshot.default"
    assert resolution.policy_provenance.strict_mode is False


def test_core_snapshot_governance_uses_policy_context() -> None:
    request = CoreSnapshotRequest(
        as_of_date=date(2026, 4, 10),
        sections=[
            CoreSnapshotSection.PORTFOLIO_STATE,
            CoreSnapshotSection.PORTFOLIO_TOTALS,
        ],
        consumer_system="request-consumer",
        tenant_id="request-tenant",
    )
    governance = SnapshotGovernanceContext(
        consumer_system="policy-consumer",
        tenant_id="policy-tenant",
        requested_sections=[
            CoreSnapshotSection.PORTFOLIO_STATE,
            CoreSnapshotSection.PORTFOLIO_TOTALS,
        ],
        applied_sections=[CoreSnapshotSection.PORTFOLIO_STATE],
        dropped_sections=[CoreSnapshotSection.PORTFOLIO_TOTALS],
        policy_version="policy.v2",
        policy_source="integration-policy",
        matched_rule_id="rule-42",
        strict_mode=True,
        warnings=["portfolio_totals dropped by policy"],
    )

    resolution = resolve_core_snapshot_governance(
        request=request,
        governance=governance,
    )

    assert resolution.consumer_system == "policy-consumer"
    assert resolution.tenant_id == "policy-tenant"
    assert resolution.requested_sections == governance.requested_sections
    assert resolution.applied_sections == [CoreSnapshotSection.PORTFOLIO_STATE]
    assert resolution.dropped_sections == [CoreSnapshotSection.PORTFOLIO_TOTALS]
    assert resolution.warnings == ["portfolio_totals dropped by policy"]
    assert resolution.policy_provenance.policy_version == "policy.v2"
    assert resolution.policy_provenance.policy_source == "integration-policy"
    assert resolution.policy_provenance.matched_rule_id == "rule-42"
    assert resolution.policy_provenance.strict_mode is True
