"""Test application-owned corporate-action reconciliation evidence."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.services.portfolio_transaction_processing_service.app.application import (
    CorporateActionReconciliationFindingType,
    CorporateActionReconciliationReasonCode,
    build_corporate_action_reconciliation_evidence,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    CorporateActionBasisReconciliationStatus,
    reconcile_corporate_action_basis,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
)


def _transaction(
    *,
    transaction_id: str,
    transaction_type: str,
    net_cost_local: str,
    allocated_cost_basis_local: str | None = None,
) -> BookedTransaction:
    return BookedTransaction(
        transaction_id=transaction_id,
        portfolio_id="PORT_COST_01",
        instrument_id="AAPL",
        security_id="SEC_COST_01",
        transaction_date=datetime(2025, 1, 15, tzinfo=UTC),
        transaction_type=transaction_type,
        quantity=Decimal(0),
        price=Decimal(0),
        gross_transaction_amount=abs(Decimal(net_cost_local)),
        trade_currency="USD",
        currency="USD",
        linked_transaction_group_id="LTG-CA-DEM-01",
        parent_event_reference="CA-PARENT-DEM-01",
        net_cost_local=Decimal(net_cost_local),
        allocated_cost_basis_local=(
            Decimal(allocated_cost_basis_local) if allocated_cost_basis_local is not None else None
        ),
        epoch=7,
    )


def _evidence(
    *transactions: BookedTransaction,
    missing_dependencies: tuple[str, ...] = (),
    completed_at: datetime = datetime(2025, 1, 16, tzinfo=UTC),
):
    processed_transaction = transactions[-1]
    return build_corporate_action_reconciliation_evidence(
        processed_transaction=processed_transaction,
        linked_transaction_group_id="LTG-CA-DEM-01",
        parent_event_reference="CA-PARENT-DEM-01",
        reconciliation=reconcile_corporate_action_basis(transactions),
        missing_dependency_reference_ids=missing_dependencies,
        correlation_id="corr-ca-01",
        completed_at=completed_at,
    )


def test_balanced_evidence_has_no_findings_and_preserves_run_contract() -> None:
    evidence = _evidence(
        _transaction(
            transaction_id="CA-OUT-01",
            transaction_type="DEMERGER_OUT",
            net_cost_local="-100",
        ),
        _transaction(
            transaction_id="CA-IN-01",
            transaction_type="DEMERGER_IN",
            net_cost_local="100",
        ),
    )

    assert evidence.run.reconciliation_type == "corporate_action_bundle_a"
    assert evidence.run.status == "COMPLETED"
    assert evidence.run.requested_by == "cost-calculator"
    assert evidence.run.business_date.isoformat() == "2025-01-15"
    assert evidence.run.epoch == 7
    assert evidence.run.correlation_id == "corr-ca-01"
    assert evidence.run.summary == {
        "examined_count": 2,
        "finding_count": 0,
        "error_count": 0,
        "warning_count": 0,
        "passed": True,
        "reconciliation_status": "balanced",
        "source_leg_count": 1,
        "target_leg_count": 1,
        "cash_consideration_count": 0,
        "source_basis_out_local": "100",
        "target_basis_in_local": "100",
        "cash_basis_local": "0",
        "net_basis_delta_local": "0",
        "missing_cash_basis_count": 0,
        "missing_dependency_count": 0,
    }
    assert evidence.findings == ()


@pytest.mark.parametrize(
    ("transactions", "expected_status", "expected_type", "expected_reason"),
    [
        (
            (
                _transaction(
                    transaction_id="CA-OUT-01",
                    transaction_type="DEMERGER_OUT",
                    net_cost_local="-100",
                ),
                _transaction(
                    transaction_id="CA-IN-01",
                    transaction_type="DEMERGER_IN",
                    net_cost_local="60",
                ),
            ),
            CorporateActionBasisReconciliationStatus.BASIS_MISMATCH,
            CorporateActionReconciliationFindingType.BASIS_MISMATCH,
            CorporateActionReconciliationReasonCode.BASIS_MISMATCH,
        ),
        (
            (
                _transaction(
                    transaction_id="CA-OUT-01",
                    transaction_type="DEMERGER_OUT",
                    net_cost_local="-100",
                ),
            ),
            CorporateActionBasisReconciliationStatus.INSUFFICIENT_LEGS,
            CorporateActionReconciliationFindingType.INSUFFICIENT_LEGS,
            CorporateActionReconciliationReasonCode.INSUFFICIENT_LEGS,
        ),
        (
            (
                _transaction(
                    transaction_id="CA-OUT-01",
                    transaction_type="DEMERGER_OUT",
                    net_cost_local="-100",
                ),
                _transaction(
                    transaction_id="CA-IN-01",
                    transaction_type="DEMERGER_IN",
                    net_cost_local="100",
                ),
                _transaction(
                    transaction_id="CA-CASH-01",
                    transaction_type="CASH_CONSIDERATION",
                    net_cost_local="0",
                ),
            ),
            CorporateActionBasisReconciliationStatus.INSUFFICIENT_CASH_BASIS,
            CorporateActionReconciliationFindingType.INSUFFICIENT_CASH_BASIS,
            CorporateActionReconciliationReasonCode.INSUFFICIENT_CASH_BASIS,
        ),
    ],
)
def test_reconciliation_status_maps_to_closed_finding_vocabulary(
    transactions: tuple[BookedTransaction, ...],
    expected_status: CorporateActionBasisReconciliationStatus,
    expected_type: CorporateActionReconciliationFindingType,
    expected_reason: CorporateActionReconciliationReasonCode,
) -> None:
    evidence = _evidence(*transactions)

    assert evidence.run.summary["reconciliation_status"] == expected_status
    assert evidence.run.summary["passed"] is False
    assert len(evidence.findings) == 1
    assert evidence.findings[0].finding_type == expected_type
    assert evidence.findings[0].severity == "ERROR"
    assert evidence.findings[0].detail["reason_code"] == expected_reason


def test_missing_dependency_adds_an_independent_error_finding() -> None:
    evidence = _evidence(
        _transaction(
            transaction_id="CA-OUT-01",
            transaction_type="DEMERGER_OUT",
            net_cost_local="-100",
        ),
        _transaction(
            transaction_id="CA-IN-01",
            transaction_type="DEMERGER_IN",
            net_cost_local="100",
        ),
        missing_dependencies=("CA-OUT-MISSING",),
    )

    assert evidence.run.summary["reconciliation_status"] == "balanced"
    assert evidence.run.summary["finding_count"] == 1
    assert evidence.run.summary["passed"] is False
    assert evidence.findings[0].finding_type == "ca_bundle_a_missing_dependency"
    assert evidence.findings[0].observed_value == {
        "missing_dependency_reference_ids": ["CA-OUT-MISSING"]
    }


def test_evidence_identity_is_stable_across_reprocessing_time() -> None:
    source = _transaction(
        transaction_id="CA-OUT-01",
        transaction_type="DEMERGER_OUT",
        net_cost_local="-100",
    )
    target = _transaction(
        transaction_id="CA-IN-01",
        transaction_type="DEMERGER_IN",
        net_cost_local="60",
    )

    first = _evidence(source, target)
    repeated = _evidence(
        source,
        replace(target),
        completed_at=datetime(2025, 2, 1, tzinfo=UTC),
    )

    assert repeated.run.run_id == first.run.run_id
    assert repeated.run.dedupe_key == first.run.dedupe_key
    assert repeated.findings[0].finding_id == first.findings[0].finding_id
    assert repeated.run.completed_at != first.run.completed_at
