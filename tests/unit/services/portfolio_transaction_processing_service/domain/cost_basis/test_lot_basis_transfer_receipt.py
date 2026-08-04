"""Verify immutable basis-transfer receipt identity and conservation invariants."""

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.domain.calculation_lineage import (
    CalculationLineage,
    build_calculation_lineage,
)
from portfolio_common.domain.cost_basis_method import CostBasisMethod

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    LotBasisTransferReceiptState,
    LotBasisTransferReceiptStatus,
    SourceLotBasisTransferAllocation,
)


def _lineage(name: str) -> CalculationLineage:
    return build_calculation_lineage(
        algorithm_id=name,
        algorithm_version=1,
        intermediate_precision=38,
        input_payload={"source": "unit-test"},
        output_payload={"amount": Decimal("25")},
    )


def _allocation(*, transferred_local: str = "25") -> SourceLotBasisTransferAllocation:
    return SourceLotBasisTransferAllocation(
        allocation_ordinal=1,
        source_lot_id="LOT-BUY-01",
        source_transaction_id="BUY-01",
        source_acquisition_date=date(2026, 1, 1),
        retained_quantity=Decimal("10"),
        source_cost_local_before=Decimal("100"),
        source_cost_base_before=Decimal("120"),
        transferred_cost_local=Decimal(transferred_local),
        transferred_cost_base=Decimal("30"),
        retained_cost_local=Decimal("100") - Decimal(transferred_local),
        retained_cost_base=Decimal("90"),
    )


def _active_receipt(*, transferred_local: str = "25") -> LotBasisTransferReceiptState:
    return LotBasisTransferReceiptState(
        source_transaction_id="SPIN-OFF-OUT-01",
        target_transaction_id="SPIN-OFF-IN-01",
        target_lot_id="LOT-SPIN-OFF-IN-01",
        portfolio_id="PORT-01",
        instrument_id="SOURCE-INSTRUMENT-01",
        security_id="SOURCE-SECURITY-01",
        transfer_timestamp=datetime(2026, 7, 1, tzinfo=timezone.utc),
        transaction_type="SPIN_OFF",
        cost_basis_method=CostBasisMethod.FIFO,
        calculation_policy_id="cost-basis-default",
        calculation_policy_version="1",
        transaction_calculation_lineage=_lineage("transaction-cost"),
        status=LotBasisTransferReceiptStatus.ACTIVE,
        transferred_cost_local=Decimal(transferred_local),
        transferred_cost_base=Decimal("30"),
        allocations=(_allocation(transferred_local=transferred_local),),
        basis_transfer_calculation_lineage=_lineage("lot-basis-transfer"),
    )


def _voided_receipt() -> LotBasisTransferReceiptState:
    return replace(
        _active_receipt(),
        status=LotBasisTransferReceiptStatus.VOIDED,
        transferred_cost_local=Decimal(0),
        transferred_cost_base=Decimal(0),
        allocations=(),
        basis_transfer_calculation_lineage=None,
        void_reason="RECALCULATED_WITHOUT_BASIS_TRANSFER",
    )


def test_receipt_identity_is_retry_stable_and_semantics_are_scale_normalized() -> None:
    compact = _active_receipt()
    persisted_scale = _active_receipt(transferred_local="25.0000000000")

    assert persisted_scale.receipt_id == compact.receipt_id
    assert persisted_scale.semantic_content_hash == compact.semantic_content_hash
    assert compact.semantic_payload()["target_transaction_id"] == "SPIN-OFF-IN-01"


def test_receipt_hash_changes_when_target_identity_changes() -> None:
    receipt = _active_receipt()
    changed_target = replace(
        receipt,
        target_transaction_id="SPIN-OFF-IN-02",
        target_lot_id="LOT-SPIN-OFF-IN-02",
    )

    assert changed_target.receipt_id == receipt.receipt_id
    assert changed_target.semantic_content_hash != receipt.semantic_content_hash


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"target_lot_id": "LOT-WRONG"}, "must derive"),
        ({"target_transaction_id": "SPIN-OFF-OUT-01"}, "must differ"),
        ({"transferred_cost_local": Decimal("24")}, "local basis does not reconcile"),
        ({"transferred_cost_base": Decimal("29")}, "base basis does not reconcile"),
        ({"allocations": ()}, "requires allocations"),
        ({"basis_transfer_calculation_lineage": None}, "requires calculation lineage"),
    ],
)
def test_active_receipt_rejects_inconsistent_evidence(
    updates: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_active_receipt(), **updates)


def test_voided_receipt_is_explicit_zero_economics_evidence() -> None:
    receipt = _voided_receipt()

    assert receipt.semantic_payload()["status"] == "VOIDED"
    assert receipt.semantic_payload()["allocations"] == []
    assert receipt.semantic_content_hash != _active_receipt().semantic_content_hash


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"transferred_cost_local": Decimal("1")}, "cannot carry economics"),
        ({"allocations": (_allocation(),)}, "cannot carry economics"),
        ({"basis_transfer_calculation_lineage": _lineage("basis")}, "cannot carry calculation"),
        ({"void_reason": "  "}, "requires a nonblank reason"),
    ],
)
def test_voided_receipt_rejects_inconsistent_evidence(
    updates: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_voided_receipt(), **updates)
