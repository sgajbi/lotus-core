"""Specify live child parking before corporate-action financial execution."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from portfolio_common.domain.calculation_lineage import canonical_content_hash

from src.services.portfolio_transaction_processing_service.app.application import (
    CorporateActionArrivalDisposition,
    ProcessTransactionCommand,
    RouteCorporateActionChildArrivalUseCase,
    TransactionEventMetadata,
)
from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    corporate_action,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    CorporateActionObservationAppendOutcome,
    CorporateActionReadinessDecision,
)

NOW = datetime(2026, 8, 11, 3, 30, tzinfo=UTC)


def _command(*, transaction_type: str = "SPIN_OFF") -> ProcessTransactionCommand:
    return ProcessTransactionCommand(
        transaction=BookedTransaction(
            transaction_id="CA-OUT-001",
            portfolio_id="PB-CA-001",
            instrument_id="INST-OLD",
            security_id="SEC-OLD",
            transaction_date=NOW,
            transaction_type=transaction_type,
            quantity=Decimal("10"),
            price=Decimal("12.50"),
            gross_transaction_amount=Decimal("125.00"),
            trade_currency="SGD",
            currency="SGD",
            economic_event_id="CA-EVENT-001",
            linked_transaction_group_id="CA-GROUP-001",
            parent_event_reference="CA-PARENT-001",
            child_role="SOURCE_POSITION_CLOSE",
            source_instrument_id="INST-OLD",
            target_instrument_id="INST-NEW",
            epoch=3,
        ),
        metadata=TransactionEventMetadata(
            event_id="transactions.persisted-4-91",
            correlation_id="corr-001",
        ),
    )


def _decision(
    status: corporate_action.CorporateActionManifestReadinessStatus,
) -> CorporateActionReadinessDecision:
    ready = status is corporate_action.CorporateActionManifestReadinessStatus.READY
    return CorporateActionReadinessDecision(
        observation_outcome=CorporateActionObservationAppendOutcome.APPENDED,
        readiness_status=status,
        manifest_content_hash=canonical_content_hash({"manifest": 1}) if ready else None,
        structural_plan_content_hash=(canonical_content_hash({"plan": 1}) if ready else None),
        ordered_transaction_ids=("CA-OUT-001",) if ready else (),
        findings=(
            ()
            if status is not corporate_action.CorporateActionManifestReadinessStatus.INVALID
            else (
                corporate_action.CorporateActionManifestFinding(
                    reason=corporate_action.CorporateActionManifestReason.INVALID_GRAPH,
                ),
            )
        ),
        state_version=4,
        through_observation_sequence=1,
    )


class _Registrar:
    def __init__(self, decision: CorporateActionReadinessDecision) -> None:
        self.decision = decision
        self.observations = []

    async def execute(self, observation):
        self.observations.append(observation)
        return self.decision


@pytest.mark.asyncio
async def test_ordinary_transaction_bypasses_graph_persistence() -> None:
    registrar = _Registrar(
        _decision(corporate_action.CorporateActionManifestReadinessStatus.AWAITING_MANIFEST)
    )
    use_case = RouteCorporateActionChildArrivalUseCase(registrar, clock=lambda: NOW)  # type: ignore[arg-type]

    result = await use_case.execute(_command(transaction_type="BUY"))

    assert result.disposition is CorporateActionArrivalDisposition.ORDINARY
    assert registrar.observations == []


@pytest.mark.asyncio
async def test_governed_child_is_parked_with_full_transaction_authority() -> None:
    registrar = _Registrar(
        _decision(corporate_action.CorporateActionManifestReadinessStatus.AWAITING_MANIFEST)
    )
    use_case = RouteCorporateActionChildArrivalUseCase(registrar, clock=lambda: NOW)  # type: ignore[arg-type]

    result = await use_case.execute(_command())

    assert result.disposition is CorporateActionArrivalDisposition.PARKED
    observation = registrar.observations[0]
    assert observation.delivery_event_id == "transactions.persisted-4-91"
    assert observation.transaction_epoch == 3
    assert observation.transaction_payload_fingerprint.startswith("sha256:")
    assert observation.observed_at == NOW


@pytest.mark.asyncio
async def test_ready_child_returns_exact_release_plan_without_financial_execution() -> None:
    registrar = _Registrar(_decision(corporate_action.CorporateActionManifestReadinessStatus.READY))
    use_case = RouteCorporateActionChildArrivalUseCase(registrar, clock=lambda: NOW)  # type: ignore[arg-type]

    result = await use_case.execute(_command())

    assert result.disposition is CorporateActionArrivalDisposition.RELEASE_READY
    assert result.plan is not None
    assert result.plan.ordered_transaction_ids == ("CA-OUT-001",)
    assert result.plan.through_observation_sequence == 1


@pytest.mark.asyncio
async def test_invalid_cohort_is_acknowledged_without_release_authority() -> None:
    registrar = _Registrar(
        _decision(corporate_action.CorporateActionManifestReadinessStatus.INVALID)
    )
    use_case = RouteCorporateActionChildArrivalUseCase(registrar, clock=lambda: NOW)  # type: ignore[arg-type]

    result = await use_case.execute(_command())

    assert result.disposition is CorporateActionArrivalDisposition.INVALID
    assert result.plan is None


@pytest.mark.asyncio
async def test_naive_arrival_clock_is_rejected() -> None:
    registrar = _Registrar(
        _decision(corporate_action.CorporateActionManifestReadinessStatus.AWAITING_MANIFEST)
    )
    use_case = RouteCorporateActionChildArrivalUseCase(  # type: ignore[arg-type]
        registrar,
        clock=lambda: datetime(2026, 8, 11, 3, 30),
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        await use_case.execute(_command())
