"""Verify immutable lot-disposal receipt identity and lifecycle invariants."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.domain.calculation_lineage import (
    CalculationLineage,
    build_calculation_lineage,
)
from portfolio_common.domain.cost_basis_method import CostBasisMethod

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    LotDisposalReceiptState,
    LotDisposalReceiptStatus,
    SourceLotDisposalAllocation,
)


def _lineage(name: str) -> CalculationLineage:
    return build_calculation_lineage(
        algorithm_id=name,
        algorithm_version=1,
        intermediate_precision=38,
        input_payload={"source": "unit-test"},
        output_payload={"amount": Decimal("10")},
    )


def _allocation(*, cost_local: str = "10") -> SourceLotDisposalAllocation:
    return SourceLotDisposalAllocation(
        source_lot_id="LOT-RECEIPT-01",
        source_transaction_id="BUY-RECEIPT-01",
        source_acquisition_date=date(2026, 1, 1),
        allocation_ordinal=1,
        consumed_quantity=Decimal("1"),
        consumed_cost_local=Decimal(cost_local),
        consumed_cost_base=Decimal("10"),
    )


def _active_receipt(
    *,
    method: CostBasisMethod = CostBasisMethod.FIFO,
    cost_local: str = "10",
) -> LotDisposalReceiptState:
    return LotDisposalReceiptState(
        disposal_transaction_id="SELL-RECEIPT-01",
        portfolio_id="PORT-RECEIPT-01",
        instrument_id="INSTRUMENT-RECEIPT-01",
        security_id="SECURITY-RECEIPT-01",
        disposal_timestamp=datetime(2026, 7, 1, tzinfo=timezone.utc),
        transaction_type="SELL",
        cost_basis_method=method,
        calculation_policy_id="cost-basis-default",
        calculation_policy_version="1",
        transaction_calculation_lineage=_lineage("transaction-cost"),
        status=LotDisposalReceiptStatus.ACTIVE,
        consumed_quantity=Decimal("1"),
        consumed_cost_local=Decimal(cost_local),
        consumed_cost_base=Decimal("10"),
        allocations=(_allocation(cost_local=cost_local),),
        disposal_calculation_lineage=_lineage("lot-disposal"),
    )


def test_receipt_identity_is_stable_while_method_changes_semantic_hash() -> None:
    fifo = _active_receipt()
    exact_retry = _active_receipt()
    avco = _active_receipt(method=CostBasisMethod.AVCO)

    assert exact_retry.receipt_id == fifo.receipt_id
    assert exact_retry.semantic_content_hash == fifo.semantic_content_hash
    assert avco.receipt_id == fifo.receipt_id
    assert avco.semantic_content_hash != fifo.semantic_content_hash


def test_receipt_semantic_hash_normalizes_persisted_decimal_scale() -> None:
    compact = _active_receipt(cost_local="10")
    persisted_scale = _active_receipt(cost_local="10.0000000000")

    assert persisted_scale.semantic_content_hash == compact.semantic_content_hash


def test_active_receipt_rejects_nonconserved_allocation_cost() -> None:
    with pytest.raises(
        ValueError,
        match="receipt allocation local cost does not reconcile",
    ):
        LotDisposalReceiptState(
            disposal_transaction_id="SELL-RECEIPT-01",
            portfolio_id="PORT-RECEIPT-01",
            instrument_id="INSTRUMENT-RECEIPT-01",
            security_id="SECURITY-RECEIPT-01",
            disposal_timestamp=datetime(2026, 7, 1, tzinfo=timezone.utc),
            transaction_type="SELL",
            cost_basis_method=CostBasisMethod.FIFO,
            calculation_policy_id=None,
            calculation_policy_version=None,
            transaction_calculation_lineage=_lineage("transaction-cost"),
            status=LotDisposalReceiptStatus.ACTIVE,
            consumed_quantity=Decimal("1"),
            consumed_cost_local=Decimal("11"),
            consumed_cost_base=Decimal("10"),
            allocations=(_allocation(),),
            disposal_calculation_lineage=_lineage("lot-disposal"),
        )


def test_voided_receipt_is_explicit_zero_economics_evidence() -> None:
    receipt = LotDisposalReceiptState(
        disposal_transaction_id="BUY-RECEIPT-01",
        portfolio_id="PORT-RECEIPT-01",
        instrument_id="INSTRUMENT-RECEIPT-01",
        security_id="SECURITY-RECEIPT-01",
        disposal_timestamp=datetime(2026, 7, 1, tzinfo=timezone.utc),
        transaction_type="BUY",
        cost_basis_method=CostBasisMethod.FIFO,
        calculation_policy_id=None,
        calculation_policy_version=None,
        transaction_calculation_lineage=_lineage("transaction-cost"),
        status=LotDisposalReceiptStatus.VOIDED,
        consumed_quantity=Decimal(0),
        consumed_cost_local=Decimal(0),
        consumed_cost_base=Decimal(0),
        allocations=(),
        disposal_calculation_lineage=None,
        void_reason="RECALCULATED_WITHOUT_LOT_DISPOSAL",
    )

    assert receipt.semantic_payload()["status"] == "VOIDED"
    assert receipt.semantic_payload()["allocations"] == []
    assert receipt.semantic_content_hash != _active_receipt().semantic_content_hash
