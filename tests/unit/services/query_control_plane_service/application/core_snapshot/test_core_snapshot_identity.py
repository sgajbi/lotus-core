from datetime import date

from src.services.query_control_plane_service.app.application.core_snapshot.governance import (
    SnapshotGovernanceContext,
    resolve_core_snapshot_governance,
)
from src.services.query_control_plane_service.app.application.core_snapshot.identity import (
    core_snapshot_identity_command_from_request,
    core_snapshot_request_fingerprint,
)
from src.services.query_control_plane_service.app.contracts.core_snapshot import (
    CoreSnapshotMode,
    CoreSnapshotRequest,
    CoreSnapshotSection,
)


def test_core_snapshot_identity_command_preserves_canonical_payload_shape() -> None:
    request = CoreSnapshotRequest(
        as_of_date=date(2026, 2, 27),
        snapshot_mode=CoreSnapshotMode.SIMULATION,
        reporting_currency="SGD",
        sections=[
            CoreSnapshotSection.POSITIONS_BASELINE,
            CoreSnapshotSection.POSITIONS_PROJECTED,
        ],
        simulation={"session_id": "SIM_1", "expected_version": 3},
        consumer_system="lotus-performance",
        tenant_id="tenant_sg_pb",
    )

    command_payload = core_snapshot_identity_command_from_request(request).canonical_payload()

    assert command_payload == request.model_dump(mode="json")


def test_core_snapshot_request_fingerprint_includes_governance_context() -> None:
    request = CoreSnapshotRequest(
        as_of_date=date(2026, 4, 10),
        snapshot_mode=CoreSnapshotMode.BASELINE,
        reporting_currency="SGD",
        sections=[
            CoreSnapshotSection.PORTFOLIO_STATE,
            CoreSnapshotSection.PORTFOLIO_TOTALS,
        ],
        consumer_system="request-consumer",
        tenant_id="request-tenant",
    )
    default_governance = resolve_core_snapshot_governance(
        request=request,
        governance=None,
    )
    policy_governance = resolve_core_snapshot_governance(
        request=request,
        governance=SnapshotGovernanceContext(
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
        ),
    )

    first = core_snapshot_request_fingerprint(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=request,
        governance=default_governance,
    )
    second = core_snapshot_request_fingerprint(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=request,
        governance=default_governance,
    )
    governed = core_snapshot_request_fingerprint(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        request=request,
        governance=policy_governance,
    )

    assert first == second
    assert governed != first
