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
    tenant_id: str = "tenant-a",
    missing_dependencies: tuple[str, ...] = (),
    completed_at: datetime = datetime(2025, 1, 16, tzinfo=UTC),
):
    processed_transaction = transactions[-1]
    return build_corporate_action_reconciliation_evidence(
        tenant_id=tenant_id,
        processed_transaction=processed_transaction,
        input_transactions=transactions,
        linked_transaction_group_id="LTG-CA-DEM-01",
        parent_event_reference="CA-PARENT-DEM-01",
        reconciliation=reconcile_corporate_action_basis(transactions),
        missing_dependency_reference_ids=missing_dependencies,
        correlation_id="corr-ca-01",
        completed_at=completed_at,
    )


def test_tenant_authority_is_part_of_deterministic_evidence_identity() -> None:
    source = _transaction(
        transaction_id="CA-OUT-TENANT",
        transaction_type="DEMERGER_OUT",
        net_cost_local="-100",
    )
    target = _transaction(
        transaction_id="CA-IN-TENANT",
        transaction_type="DEMERGER_IN",
        net_cost_local="100",
    )

    tenant_a = _evidence(source, target, tenant_id="tenant-a")
    tenant_b = _evidence(source, target, tenant_id="tenant-b")

    assert tenant_a.tenant_id == "tenant-a"
    assert tenant_b.tenant_id == "tenant-b"
    assert tenant_a.run.run_id != tenant_b.run.run_id
    assert tenant_a.run.dedupe_key != tenant_b.run.dedupe_key


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
        "fractional_cash_leg_count": 0,
        "source_basis_out_local": "100",
        "target_basis_in_local": "100",
        "target_basis_retained_local": "100",
        "cash_basis_local": "0",
        "cash_consideration_basis_local": "0",
        "fractional_basis_local": "0",
        "net_basis_delta_local": "0",
        "missing_cash_basis_count": 0,
        "excluded_cash_settlement_adjustment_count": 0,
        "unsupported_adjustment_count": 0,
        "governed_adjustment_basis_local": "0",
        "missing_dependency_count": 0,
        "linkage_finding_count": 0,
        "linked_transaction_group_id": "LTG-CA-DEM-01",
        "parent_event_reference": "CA-PARENT-DEM-01",
        "reconciliation_policy_id": "CORPORATE_ACTION_BASIS_CONSERVATION",
        "reconciliation_policy_version": "1.0.0",
        "input_lineage": evidence.run.summary["input_lineage"],
    }
    assert evidence.findings == ()
    assert [item["transaction_id"] for item in evidence.run.summary["input_lineage"]] == [
        "CA-IN-01",
        "CA-OUT-01",
    ]
    assert all(
        item["payload_fingerprint"].startswith("sha256:")
        and item["semantic_key"].startswith("transaction-processing:v1:")
        and item["epoch"] == 7
        for item in evidence.run.summary["input_lineage"]
    )


def test_fractional_cash_basis_is_explicit_in_reconciliation_evidence() -> None:
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
        _transaction(
            transaction_id="CA-CIL-01",
            transaction_type="CASH_IN_LIEU",
            net_cost_local="-10",
            allocated_cost_basis_local="10",
        ),
    )

    assert evidence.run.summary["reconciliation_status"] == "balanced"
    assert evidence.run.summary["fractional_cash_leg_count"] == 1
    assert evidence.run.summary["fractional_basis_local"] == "10"
    assert evidence.run.summary["target_basis_retained_local"] == "90"
    assert evidence.run.summary["cash_consideration_basis_local"] == "0"
    assert evidence.run.summary["cash_basis_local"] == "10"
    assert evidence.run.summary["examined_count"] == 3


def test_ambiguous_adjustment_emits_stable_unsupported_reason() -> None:
    source = _transaction(
        transaction_id="CA-OUT-01", transaction_type="SPIN_OFF", net_cost_local="-100"
    )
    target = _transaction(
        transaction_id="CA-IN-01", transaction_type="SPIN_IN", net_cost_local="100"
    )
    adjustment = replace(
        _transaction(transaction_id="CA-ADJ-01", transaction_type="ADJUSTMENT", net_cost_local="5"),
        adjustment_reason="MANUAL_BASIS_OVERRIDE",
        movement_direction="INFLOW",
    )

    evidence = _evidence(source, target, adjustment)

    assert evidence.run.summary["reconciliation_status"] == "unsupported_adjustment"
    assert evidence.run.summary["unsupported_adjustment_count"] == 1
    assert evidence.run.summary["governed_adjustment_basis_local"] == "0"
    assert evidence.findings[0].detail["reason_code"] == (
        "CA_BUNDLE_A_UNSUPPORTED_BASIS_ADJUSTMENT"
    )
    assert evidence.findings[0].repair_recommendation == (
        "REBOOK_WITH_SUPPORTED_CORPORATE_ACTION_BASIS_LEGS"
    )


@pytest.mark.parametrize(
    ("transactions", "expected_status", "expected_finding_types"),
    [
        (
            (
                _transaction(
                    transaction_id="CA-OUT-01",
                    transaction_type="SPIN_OFF",
                    net_cost_local="-100",
                ),
                replace(
                    _transaction(
                        transaction_id="CA-ADJ-01",
                        transaction_type="ADJUSTMENT",
                        net_cost_local="5",
                    ),
                    adjustment_reason="MANUAL_BASIS_OVERRIDE",
                    movement_direction="INFLOW",
                ),
            ),
            CorporateActionBasisReconciliationStatus.INSUFFICIENT_LEGS,
            (
                CorporateActionReconciliationFindingType.INSUFFICIENT_LEGS,
                CorporateActionReconciliationFindingType.UNSUPPORTED_ADJUSTMENT,
            ),
        ),
        (
            (
                _transaction(
                    transaction_id="CA-OUT-01",
                    transaction_type="SPIN_OFF",
                    net_cost_local="-100",
                ),
                _transaction(
                    transaction_id="CA-IN-01",
                    transaction_type="SPIN_IN",
                    net_cost_local="100",
                ),
                _transaction(
                    transaction_id="CA-CASH-01",
                    transaction_type="CASH_CONSIDERATION",
                    net_cost_local="0",
                ),
                replace(
                    _transaction(
                        transaction_id="CA-ADJ-01",
                        transaction_type="ADJUSTMENT",
                        net_cost_local="5",
                    ),
                    adjustment_reason="MANUAL_BASIS_OVERRIDE",
                    movement_direction="INFLOW",
                ),
            ),
            CorporateActionBasisReconciliationStatus.INSUFFICIENT_CASH_BASIS,
            (
                CorporateActionReconciliationFindingType.INSUFFICIENT_CASH_BASIS,
                CorporateActionReconciliationFindingType.UNSUPPORTED_ADJUSTMENT,
            ),
        ),
        (
            (
                _transaction(
                    transaction_id="CA-OUT-01",
                    transaction_type="SPIN_OFF",
                    net_cost_local="-100",
                ),
                _transaction(
                    transaction_id="CA-IN-01",
                    transaction_type="SPIN_IN",
                    net_cost_local="100",
                ),
                _transaction(
                    transaction_id="CA-CIL-01",
                    transaction_type="CASH_IN_LIEU",
                    net_cost_local="-110",
                    allocated_cost_basis_local="110",
                ),
                replace(
                    _transaction(
                        transaction_id="CA-ADJ-01",
                        transaction_type="ADJUSTMENT",
                        net_cost_local="5",
                    ),
                    adjustment_reason="MANUAL_BASIS_OVERRIDE",
                    movement_direction="INFLOW",
                ),
            ),
            CorporateActionBasisReconciliationStatus.INVALID_BASIS_ALLOCATION,
            (
                CorporateActionReconciliationFindingType.INVALID_BASIS_ALLOCATION,
                CorporateActionReconciliationFindingType.UNSUPPORTED_ADJUSTMENT,
            ),
        ),
        (
            (
                _transaction(
                    transaction_id="CA-OUT-01",
                    transaction_type="SPIN_OFF",
                    net_cost_local="-100",
                ),
                _transaction(
                    transaction_id="CA-CASH-01",
                    transaction_type="CASH_CONSIDERATION",
                    net_cost_local="0",
                ),
            ),
            CorporateActionBasisReconciliationStatus.INSUFFICIENT_LEGS,
            (
                CorporateActionReconciliationFindingType.INSUFFICIENT_LEGS,
                CorporateActionReconciliationFindingType.INSUFFICIENT_CASH_BASIS,
            ),
        ),
    ],
)
def test_independently_counted_defects_emit_additive_deterministic_findings(
    transactions: tuple[BookedTransaction, ...],
    expected_status: CorporateActionBasisReconciliationStatus,
    expected_finding_types: tuple[CorporateActionReconciliationFindingType, ...],
) -> None:
    evidence = _evidence(*transactions)
    replayed = _evidence(*reversed(transactions))

    assert evidence.run.summary["reconciliation_status"] == expected_status
    assert tuple(finding.finding_type for finding in evidence.findings) == (expected_finding_types)
    assert evidence.run.summary["finding_count"] == len(evidence.findings)
    assert evidence.run.summary["error_count"] == len(evidence.findings)
    assert evidence.run.summary["passed"] is False
    assert len({finding.finding_id for finding in evidence.findings}) == len(evidence.findings)
    assert replayed.run.run_id == evidence.run.run_id
    assert tuple(finding.finding_id for finding in replayed.findings) == tuple(
        finding.finding_id for finding in evidence.findings
    )


def test_negative_retained_target_basis_emits_stable_allocation_finding() -> None:
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
        _transaction(
            transaction_id="CA-CIL-01",
            transaction_type="CASH_IN_LIEU",
            net_cost_local="-110",
            allocated_cost_basis_local="110",
        ),
    )

    assert evidence.run.summary["reconciliation_status"] == "invalid_basis_allocation"
    assert evidence.run.summary["target_basis_retained_local"] == "-10"
    assert len(evidence.findings) == 1
    finding = evidence.findings[0]
    assert finding.finding_type == "ca_bundle_a_invalid_basis_allocation"
    assert finding.detail["reason_code"] == "CA_BUNDLE_A_INVALID_BASIS_ALLOCATION"
    assert finding.expected_value == {"target_basis_retained_local": ">= 0"}
    assert finding.observed_value == {
        "target_basis_in_local": "100",
        "fractional_basis_local": "110",
        "target_basis_retained_local": "-10",
    }
    assert finding.repair_recommendation == "REPAIR_FRACTIONAL_BASIS_ALLOCATION"


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
    assert evidence.findings[0].owner == "CORPORATE_ACTION_OPERATIONS"
    assert evidence.findings[0].resolution_state == "OPEN"
    assert evidence.findings[0].tolerance == Decimal("0.01")
    assert evidence.findings[0].repair_recommendation
    assert evidence.findings[0].observed_delta == (
        Decimal("-40")
        if expected_type is CorporateActionReconciliationFindingType.BASIS_MISMATCH
        else None
    )


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
    assert evidence.findings[0].repair_recommendation == ("RESTORE_CORPORATE_ACTION_DEPENDENCY")


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


def test_evidence_identity_is_child_order_independent() -> None:
    source = _transaction(
        transaction_id="CA-OUT-01",
        transaction_type="DEMERGER_OUT",
        net_cost_local="-100",
    )
    first_target = _transaction(
        transaction_id="CA-IN-01",
        transaction_type="DEMERGER_IN",
        net_cost_local="40",
    )
    second_target = replace(
        _transaction(
            transaction_id="CA-IN-02",
            transaction_type="DEMERGER_IN",
            net_cost_local="60",
        ),
        epoch=8,
    )

    first = _evidence(source, first_target, second_target)
    reordered = _evidence(second_target, source, first_target)

    assert reordered.run.run_id == first.run.run_id
    assert reordered.run.dedupe_key == first.run.dedupe_key
    assert reordered.run.summary["input_lineage"] == first.run.summary["input_lineage"]
    assert reordered.run.business_date == first.run.business_date
    assert reordered.run.epoch == first.run.epoch


@pytest.mark.parametrize(
    "changed_target",
    [
        {"transaction_id": "CA-IN-REBOOKED"},
        {"gross_transaction_amount": Decimal("61")},
        {"epoch": 8},
        {"calculation_policy_id": "CA-BASIS-POLICY"},
        {"calculation_policy_version": "2.0.0"},
    ],
)
def test_evidence_identity_binds_child_identity_economics_revision_and_policy(
    changed_target: dict[str, object],
) -> None:
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
    baseline = _evidence(source, target)

    changed = _evidence(source, replace(target, **changed_target))

    assert changed.run.run_id != baseline.run.run_id
    assert changed.run.summary["input_lineage"] != baseline.run.summary["input_lineage"]
