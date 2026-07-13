"""Application tests for corporate-action group reconciliation coordination."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

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
    ).reconcile(transaction, correlation_id="corr-01")

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

    first = await coordinator.reconcile(source, correlation_id="corr-01")
    repeated = await coordinator.reconcile(target, correlation_id="corr-01")

    assert first is not None
    assert repeated is None
    assert repository.loaded_keys == [
        CorporateActionReconciliationKey(
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
            source_basis_out_local=Decimal("100"),
            target_basis_in_local=Decimal("100"),
            cash_basis_local=Decimal("0"),
            missing_cash_basis_count=0,
            net_basis_delta_local=Decimal("0"),
            basis_tolerance=Decimal("0.01"),
            missing_dependency_reference_ids=(),
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
    ).reconcile(source, correlation_id=None)

    assert evidence is not None
    assert evidence.run.summary["missing_dependency_count"] == 1
    assert evidence.findings[-1].detail["missing_dependency_reference_ids"] == ["CA-IN-MISSING"]
    assert observer.observations[0].missing_dependency_reference_ids == ("CA-IN-MISSING",)


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
        await coordinator.reconcile(source, correlation_id="corr-01")

    repository.save_error = None
    evidence = await coordinator.reconcile(source, correlation_id="corr-01")

    assert evidence is not None
    assert len(repository.loaded_keys) == 2
    assert len(repository.saved_evidence) == 1
    assert len(observer.observations) == 1
