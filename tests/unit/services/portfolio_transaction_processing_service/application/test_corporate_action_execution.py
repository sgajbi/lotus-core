"""Specify fail-closed corporate-action runtime execution authority."""

from datetime import UTC, datetime

import pytest
from portfolio_common.domain.calculation_lineage import canonical_content_hash

from src.services.portfolio_transaction_processing_service.app.application import (
    CorporateActionExecutionDisposition,
    resolve_corporate_action_execution_gate,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction.corporate_action import (  # noqa: E501
    CorporateActionEventChild,
    CorporateActionManifestFinding,
    CorporateActionManifestReadinessStatus,
    CorporateActionManifestReason,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    CorporateActionChildObservation,
    CorporateActionObservationAppendOutcome,
    CorporateActionReadinessDecision,
)


def _observation() -> CorporateActionChildObservation:
    return CorporateActionChildObservation(
        corporate_action_event_id="CA-EVENT-001",
        portfolio_id="PORT-CA-001",
        linked_transaction_group_id="GROUP-CA-001",
        parent_event_reference="PARENT-CA-001",
        child=CorporateActionEventChild(
            transaction_id="CA-TARGET-001",
            transaction_type="SPIN_IN",
            child_role="TARGET_POSITION_OPEN",
            dependency_transaction_ids=("CA-SOURCE-001",),
            source_instrument_id="SEC-SOURCE-001",
            target_instrument_id="SEC-TARGET-001",
        ),
        transaction_epoch=1,
        delivery_event_id="transactions.persisted-0-1",
        correlation_id="corr-ca-001",
        observed_at=datetime(2026, 8, 11, 10, 0, tzinfo=UTC),
    )


def _decision(
    status: CorporateActionManifestReadinessStatus,
    *,
    manifest_content_hash: str | None = None,
    ordered_transaction_ids: tuple[str, ...] = (),
    findings: tuple[CorporateActionManifestFinding, ...] = (),
) -> CorporateActionReadinessDecision:
    return CorporateActionReadinessDecision(
        observation_outcome=CorporateActionObservationAppendOutcome.APPENDED,
        readiness_status=status,
        manifest_content_hash=manifest_content_hash,
        ordered_transaction_ids=ordered_transaction_ids,
        findings=findings,
        state_version=7,
        through_observation_sequence=3,
    )


@pytest.mark.parametrize(
    "status",
    [
        CorporateActionManifestReadinessStatus.AWAITING_MANIFEST,
        CorporateActionManifestReadinessStatus.AWAITING_COMPLETION,
        CorporateActionManifestReadinessStatus.AWAITING_CHILDREN,
    ],
)
def test_incomplete_readiness_is_parked_without_execution_authority(
    status: CorporateActionManifestReadinessStatus,
) -> None:
    finding = CorporateActionManifestFinding(
        CorporateActionManifestReason.MISSING_EXPECTED_CHILD,
        transaction_ids=("CA-SOURCE-001",),
    )

    gate = resolve_corporate_action_execution_gate(
        _observation(),
        _decision(status, findings=(finding,)),
    )

    assert gate.disposition is CorporateActionExecutionDisposition.PARKED
    assert gate.plan is None
    assert gate.findings == (finding,)


def test_invalid_readiness_is_not_reclassified_as_parked() -> None:
    finding = CorporateActionManifestFinding(
        CorporateActionManifestReason.OBSERVED_CHILD_MISMATCH,
        transaction_ids=("CA-TARGET-001",),
    )

    gate = resolve_corporate_action_execution_gate(
        _observation(),
        _decision(CorporateActionManifestReadinessStatus.INVALID, findings=(finding,)),
    )

    assert gate.disposition is CorporateActionExecutionDisposition.INVALID
    assert gate.plan is None


def test_ready_decision_builds_stable_source_bound_execution_plan() -> None:
    manifest_hash = canonical_content_hash({"manifest": "CA-EVENT-001", "version": 2})
    decision = _decision(
        CorporateActionManifestReadinessStatus.READY,
        manifest_content_hash=manifest_hash,
        ordered_transaction_ids=("CA-SOURCE-001", "CA-TARGET-001"),
    )

    first = resolve_corporate_action_execution_gate(_observation(), decision)
    replayed = resolve_corporate_action_execution_gate(_observation(), decision)

    assert first.disposition is CorporateActionExecutionDisposition.READY
    assert first.plan is not None
    assert replayed.plan is not None
    assert first.plan.manifest_content_hash == manifest_hash
    assert first.plan.ordered_transaction_ids == ("CA-SOURCE-001", "CA-TARGET-001")
    assert first.plan.execution_plan_hash == replayed.plan.execution_plan_hash
    assert len(first.plan.execution_plan_hash) == 64


@pytest.mark.parametrize(
    "decision",
    [
        _decision(
            CorporateActionManifestReadinessStatus.READY,
            ordered_transaction_ids=("CA-SOURCE-001", "CA-TARGET-001"),
        ),
        _decision(
            CorporateActionManifestReadinessStatus.READY,
            manifest_content_hash=canonical_content_hash({"manifest": "CA-EVENT-001"}),
            ordered_transaction_ids=("CA-SOURCE-001", "CA-SOURCE-001"),
        ),
        _decision(
            CorporateActionManifestReadinessStatus.AWAITING_CHILDREN,
            manifest_content_hash=canonical_content_hash({"manifest": "CA-EVENT-001"}),
        ),
    ],
)
def test_contradictory_or_incomplete_release_authority_fails_closed(
    decision: CorporateActionReadinessDecision,
) -> None:
    with pytest.raises(ValueError):
        resolve_corporate_action_execution_gate(_observation(), decision)
