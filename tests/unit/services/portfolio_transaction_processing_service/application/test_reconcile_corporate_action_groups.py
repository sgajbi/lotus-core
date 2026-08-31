"""Application tests for corporate-action group reconciliation coordination."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from time import perf_counter

import pytest

from src.services.portfolio_transaction_processing_service.app.application import (
    CorporateActionReconciliationCoordinator,
)
from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.ports import (
    CorporateActionReconciliationEvidence,
    CorporateActionReconciliationKey,
    CorporateActionReconciliationObservation,
)

pytestmark = pytest.mark.asyncio
TENANT_ID = "tenant-a"


def _transaction(
    *,
    transaction_id: str,
    transaction_type: str,
    net_cost_local: str,
    dependency_reference_ids: tuple[str, ...] | None = None,
) -> BookedTransaction:
    return BookedTransaction(
        transaction_id=transaction_id,
        portfolio_id="PORT_CA_01",
        instrument_id="AAPL",
        security_id="SEC_CA_01",
        transaction_date=datetime(2026, 4, 10, tzinfo=UTC),
        transaction_type=transaction_type,
        quantity=Decimal(0),
        price=Decimal(0),
        gross_transaction_amount=abs(Decimal(net_cost_local)),
        trade_currency="USD",
        currency="USD",
        linked_transaction_group_id="LTG-CA-01",
        parent_event_reference="CA-PARENT-01",
        dependency_reference_ids=dependency_reference_ids,
        net_cost_local=Decimal(net_cost_local),
        epoch=9,
    )


class _Repository:
    def __init__(self, transactions: tuple[BookedTransaction, ...]) -> None:
        self.transactions = transactions
        self.loaded_keys: list[CorporateActionReconciliationKey] = []
        self.saved_evidence: list[CorporateActionReconciliationEvidence] = []
        self.save_error: Exception | None = None

    async def load_group(
        self, key: CorporateActionReconciliationKey
    ) -> tuple[BookedTransaction, ...]:
        self.loaded_keys.append(key)
        return self.transactions

    async def save_evidence(self, evidence: CorporateActionReconciliationEvidence) -> None:
        if self.save_error is not None:
            raise self.save_error
        self.saved_evidence.append(evidence)


class _Observer:
    def __init__(self) -> None:
        self.observations: list[CorporateActionReconciliationObservation] = []

    def observe(self, observation: CorporateActionReconciliationObservation) -> None:
        self.observations.append(observation)


async def test_non_corporate_action_does_not_cross_reconciliation_port() -> None:
    transaction = _transaction(
        transaction_id="BUY-01",
        transaction_type="BUY",
        net_cost_local="100",
    )
    repository = _Repository((transaction,))
    observer = _Observer()

    result = await CorporateActionReconciliationCoordinator(
        repository,
        observer=observer,
    ).reconcile(transaction, tenant_id=TENANT_ID, correlation_id="corr-01")

    assert result is None
    assert repository.loaded_keys == []
    assert repository.saved_evidence == []
    assert observer.observations == []


async def test_incomplete_group_identity_does_not_cross_reconciliation_port() -> None:
    transaction = _transaction(
        transaction_id="CA-OUT-01",
        transaction_type="DEMERGER_OUT",
        net_cost_local="-100",
    )
    transaction = replace(transaction, parent_event_reference=None)
    repository = _Repository((transaction,))

    result = await CorporateActionReconciliationCoordinator(repository).reconcile(
        transaction,
        tenant_id=TENANT_ID,
        correlation_id="corr-01",
    )

    assert result is None
    assert repository.loaded_keys == []


async def test_group_is_loaded_persisted_and_observed_once_per_batch() -> None:
    source = _transaction(
        transaction_id="CA-OUT-01",
        transaction_type="DEMERGER_OUT",
        net_cost_local="-100",
    )
    target = _transaction(
        transaction_id="CA-IN-01",
        transaction_type="DEMERGER_IN",
        net_cost_local="100",
    )
    repository = _Repository((source, target))
    observer = _Observer()
    completed_at = datetime(2026, 4, 10, 12, 30, tzinfo=UTC)
    coordinator = CorporateActionReconciliationCoordinator(
        repository,
        observer=observer,
        clock=lambda: completed_at,
    )

    first = await coordinator.reconcile(source, tenant_id=TENANT_ID, correlation_id="corr-01")
    repeated = await coordinator.reconcile(target, tenant_id=TENANT_ID, correlation_id="corr-01")

    assert first is not None
    assert repeated is None
    assert repository.loaded_keys == [
        CorporateActionReconciliationKey(
            tenant_id=TENANT_ID,
            portfolio_id="PORT_CA_01",
            linked_transaction_group_id="LTG-CA-01",
            parent_event_reference="CA-PARENT-01",
        )
    ]
    assert repository.saved_evidence == [first]
    assert first.run.completed_at == completed_at
    assert first.run.summary["reconciliation_status"] == "balanced"
    assert observer.observations == [
        CorporateActionReconciliationObservation(
            key=repository.loaded_keys[0],
            processed_transaction=source,
            reconciliation_status="balanced",
            source_leg_count=1,
            target_leg_count=1,
            cash_consideration_count=0,
            fractional_cash_leg_count=0,
            source_basis_out_local=Decimal("100"),
            target_basis_in_local=Decimal("100"),
            target_basis_retained_local=Decimal("100"),
            cash_basis_local=Decimal("0"),
            cash_consideration_basis_local=Decimal("0"),
            fractional_basis_local=Decimal("0"),
            missing_cash_basis_count=0,
            excluded_cash_settlement_adjustment_count=0,
            unsupported_adjustment_count=0,
            net_basis_delta_local=Decimal("0"),
            basis_tolerance=Decimal("0.01"),
            missing_dependency_reference_ids=(),
            linkage_finding_count=0,
            finding_severities=(),
        )
    ]


async def test_missing_dependency_is_carried_to_evidence_and_observation() -> None:
    source = _transaction(
        transaction_id="CA-OUT-01",
        transaction_type="DEMERGER_OUT",
        net_cost_local="-100",
        dependency_reference_ids=("CA-IN-MISSING",),
    )
    repository = _Repository((source,))
    observer = _Observer()

    evidence = await CorporateActionReconciliationCoordinator(
        repository,
        observer=observer,
    ).reconcile(source, tenant_id=TENANT_ID, correlation_id=None)

    assert evidence is not None
    assert evidence.run.summary["missing_dependency_count"] == 1
    assert evidence.findings[-1].detail["missing_dependency_reference_ids"] == ["CA-IN-MISSING"]
    assert observer.observations[0].missing_dependency_reference_ids == ("CA-IN-MISSING",)


async def test_quantity_transfer_group_emits_reciprocal_linkage_evidence() -> None:
    source = replace(
        _transaction(
            transaction_id="EXCHANGE-OUT-01",
            transaction_type="EXCHANGE_OUT",
            net_cost_local="-100",
        ),
        instrument_id="SOURCE-INSTRUMENT-01",
        source_instrument_id="SOURCE-INSTRUMENT-01",
        target_instrument_id="TARGET-INSTRUMENT-01",
        target_transaction_reference="EXCHANGE-IN-01",
    )
    target = replace(
        _transaction(
            transaction_id="EXCHANGE-IN-01",
            transaction_type="EXCHANGE_IN",
            net_cost_local="100",
        ),
        instrument_id="TARGET-INSTRUMENT-01",
        source_instrument_id="SOURCE-INSTRUMENT-01",
        target_instrument_id="TARGET-INSTRUMENT-01",
        source_transaction_reference="WRONG-SOURCE",
    )
    repository = _Repository((source, target))
    observer = _Observer()

    evidence = await CorporateActionReconciliationCoordinator(
        repository,
        observer=observer,
    ).reconcile(source, tenant_id=TENANT_ID, correlation_id="corr-linkage-01")

    assert evidence is not None
    assert evidence.run.reconciliation_type == "corporate_action_quantity_transfer"
    assert evidence.run.summary["linkage_finding_count"] == 2
    assert evidence.run.summary["passed"] is False
    assert [finding.finding_type for finding in evidence.findings] == [
        "ca_linked_leg_mismatch",
        "ca_linked_leg_mismatch",
    ]
    assert evidence.findings[0].detail["linkage_finding_type"] == ("transaction_reference_mismatch")
    assert observer.observations[0].linkage_finding_count == 2


async def test_late_source_adjustment_triggers_unsupported_adjustment_evidence() -> None:
    source = _transaction(
        transaction_id="CA-OUT-01",
        transaction_type="DEMERGER_OUT",
        net_cost_local="-100",
    )
    target = _transaction(
        transaction_id="CA-IN-01",
        transaction_type="DEMERGER_IN",
        net_cost_local="100",
    )
    adjustment = replace(
        _transaction(
            transaction_id="CA-ADJUSTMENT-01",
            transaction_type="ADJUSTMENT",
            net_cost_local="5",
        ),
        adjustment_reason="MANUAL_BASIS_OVERRIDE",
        movement_direction="INFLOW",
    )
    repository = _Repository((source, target, adjustment))

    evidence = await CorporateActionReconciliationCoordinator(repository).reconcile(
        adjustment,
        tenant_id=TENANT_ID,
        correlation_id="corr-late-adjustment-01",
    )

    assert evidence is not None
    assert evidence.run.reconciliation_type == "corporate_action_bundle_a"
    assert evidence.run.summary["reconciliation_status"] == "unsupported_adjustment"
    assert evidence.run.summary["unsupported_adjustment_count"] == 1
    assert [finding.finding_type for finding in evidence.findings] == [
        "ca_bundle_a_unsupported_adjustment"
    ]
    assert repository.loaded_keys == [
        CorporateActionReconciliationKey(
            tenant_id=TENANT_ID,
            portfolio_id="PORT_CA_01",
            linked_transaction_group_id="LTG-CA-01",
            parent_event_reference="CA-PARENT-01",
        )
    ]


@pytest.mark.parametrize(
    ("overlay_type", "target_basis", "summary_count"),
    [
        ("CASH_IN_LIEU", "100", "fractional_cash_leg_count"),
        ("CASH_CONSIDERATION", "90", "cash_consideration_count"),
    ],
)
async def test_cash_overlay_uses_loaded_quantity_transfer_family(
    overlay_type: str,
    target_basis: str,
    summary_count: str,
) -> None:
    source = _transaction(
        transaction_id="MERGER-OUT-01",
        transaction_type="MERGER_OUT",
        net_cost_local="-100",
    )
    target = _transaction(
        transaction_id="MERGER-IN-01",
        transaction_type="MERGER_IN",
        net_cost_local=target_basis,
    )
    corrected_cash = replace(
        _transaction(
            transaction_id="MERGER-CIL-01",
            transaction_type=overlay_type,
            net_cost_local="-10",
        ),
        allocated_cost_basis_local=Decimal("10"),
        epoch=10,
    )
    repository = _Repository((source, target, corrected_cash))

    evidence = await CorporateActionReconciliationCoordinator(repository).reconcile(
        corrected_cash,
        tenant_id=TENANT_ID,
        correlation_id="corr-corrected-cash-01",
    )

    assert evidence is not None
    assert evidence.run.reconciliation_type == "corporate_action_quantity_transfer"
    assert evidence.run.summary["reconciliation_status"] == "balanced"
    assert evidence.run.summary[summary_count] == 1


async def test_failed_persistence_is_not_observed_or_deduplicated() -> None:
    source = _transaction(
        transaction_id="CA-OUT-01",
        transaction_type="DEMERGER_OUT",
        net_cost_local="-100",
    )
    repository = _Repository((source,))
    repository.save_error = RuntimeError("database unavailable")
    observer = _Observer()
    coordinator = CorporateActionReconciliationCoordinator(repository, observer=observer)

    with pytest.raises(RuntimeError, match="database unavailable"):
        await coordinator.reconcile(source, tenant_id=TENANT_ID, correlation_id="corr-01")

    repository.save_error = None
    evidence = await coordinator.reconcile(source, tenant_id=TENANT_ID, correlation_id="corr-01")

    assert evidence is not None
    assert len(repository.loaded_keys) == 2
    assert len(repository.saved_evidence) == 1
    assert len(observer.observations) == 1


async def test_one_thousand_target_group_uses_one_read_and_one_evidence_write() -> None:
    source = _transaction(
        transaction_id="CA-OUT-CAPACITY",
        transaction_type="DEMERGER_OUT",
        net_cost_local="-1000",
    )
    targets = tuple(
        _transaction(
            transaction_id=f"CA-IN-CAPACITY-{ordinal:04d}",
            transaction_type="DEMERGER_IN",
            net_cost_local="1",
        )
        for ordinal in range(1_000)
    )
    repository = _Repository((source, *targets))

    started_at = perf_counter()
    evidence = await CorporateActionReconciliationCoordinator(repository).reconcile(
        source,
        tenant_id=TENANT_ID,
        correlation_id="corr-capacity-1000",
    )
    elapsed_seconds = perf_counter() - started_at

    assert evidence is not None
    assert evidence.run.summary["reconciliation_status"] == "balanced"
    assert evidence.run.summary["target_leg_count"] == 1_000
    assert evidence.run.summary["examined_count"] == 1_001
    assert len(evidence.run.summary["input_lineage"]) == 1_001
    assert len(repository.loaded_keys) == 1
    assert repository.saved_evidence == [evidence]
    assert elapsed_seconds < 5.0
