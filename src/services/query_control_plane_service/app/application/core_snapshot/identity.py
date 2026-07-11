"""Build deterministic Core snapshot request fingerprints."""

from __future__ import annotations

from typing import Any, cast

from portfolio_common.request_fingerprints import request_fingerprint

from ...contracts.core_snapshot import CoreSnapshotRequest
from .governance import CoreSnapshotGovernanceResolution
from .identity_command import (
    CoreSnapshotIdentityCommand,
    CoreSnapshotOptionsCommand,
    CoreSnapshotSimulationCommand,
)


def core_snapshot_identity_command_from_request(
    request: CoreSnapshotRequest,
) -> CoreSnapshotIdentityCommand:
    return CoreSnapshotIdentityCommand(
        as_of_date=request.as_of_date,
        snapshot_mode=request.snapshot_mode.value,
        reporting_currency=request.reporting_currency,
        consumer_system=request.consumer_system,
        tenant_id=request.tenant_id,
        sections=[section.value for section in request.sections],
        simulation=(
            CoreSnapshotSimulationCommand(
                session_id=request.simulation.session_id,
                expected_version=request.simulation.expected_version,
            )
            if request.simulation is not None
            else None
        ),
        options=CoreSnapshotOptionsCommand(
            include_zero_quantity_positions=(request.options.include_zero_quantity_positions),
            include_cash_positions=request.options.include_cash_positions,
            position_basis=request.options.position_basis.value,
            weight_basis=request.options.weight_basis.value,
        ),
    )


def core_snapshot_request_fingerprint(
    *,
    portfolio_id: str,
    request: CoreSnapshotRequest,
    governance: CoreSnapshotGovernanceResolution,
) -> str:
    return _request_fingerprint(
        {
            "portfolio_id": portfolio_id,
            "request": core_snapshot_identity_command_from_request(request).canonical_payload(),
            "governance": {
                "consumer_system": governance.consumer_system,
                "tenant_id": governance.tenant_id,
                "requested_sections": [section.value for section in governance.requested_sections],
                "applied_sections": [section.value for section in governance.applied_sections],
                "dropped_sections": [section.value for section in governance.dropped_sections],
                "policy_version": governance.policy_provenance.policy_version,
                "policy_source": governance.policy_provenance.policy_source,
                "matched_rule_id": governance.policy_provenance.matched_rule_id,
                "strict_mode": governance.policy_provenance.strict_mode,
                "warnings": governance.warnings,
            },
        }
    )


def _request_fingerprint(payload: dict[str, Any]) -> str:
    return cast(str, request_fingerprint(payload))
