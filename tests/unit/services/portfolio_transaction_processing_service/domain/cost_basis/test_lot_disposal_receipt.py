"""Verify immutable lot-disposal receipt identity and lifecycle invariants."""

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
    LotDisposalDestination,
    LotDisposalDestinationType,
    LotDisposalReceiptState,
    LotDisposalReceiptStatus,
    SourceLotDisposalAllocation,
)


def _internal_destination() -> LotDisposalDestination:
    return LotDisposalDestination(
        destination_type=LotDisposalDestinationType.INTERNAL_LOT,
        target_transaction_id="EXCHANGE-IN-01",
        target_lot_id="LOT-EXCHANGE-IN-01",
        target_instrument_id="TARGET-INSTRUMENT-01",
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


def _voided_receipt() -> LotDisposalReceiptState:
    return LotDisposalReceiptState(
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


def test_receipt_identity_is_stable_while_method_changes_semantic_hash() -> None:
    fifo = _active_receipt()
    exact_retry = _active_receipt()
    avco = _active_receipt(method=CostBasisMethod.AVCO)

    assert exact_retry.receipt_id == fifo.receipt_id
    assert exact_retry.semantic_content_hash == fifo.semantic_content_hash
    assert avco.receipt_id == fifo.receipt_id
    assert avco.semantic_content_hash != fifo.semantic_content_hash


def test_absent_destination_preserves_legacy_terminal_receipt_hash() -> None:
    receipt = _active_receipt()

    assert "destination" not in receipt.semantic_payload()
    assert receipt.semantic_content_hash == (
        "a0a2afd31f3c3947511100b7ef6f06d0315303a58235e590530ca84d7ac1179a"
    )


def test_internal_destination_is_normalized_and_changes_semantic_identity() -> None:
    destination = replace(
        _internal_destination(),
        target_transaction_id="  EXCHANGE-IN-01  ",
        target_lot_id="  LOT-EXCHANGE-IN-01  ",
        target_instrument_id="  TARGET-INSTRUMENT-01  ",
    )
    receipt = replace(_active_receipt(), destination=destination)

    assert destination.target_transaction_id == "EXCHANGE-IN-01"
    assert receipt.receipt_id == _active_receipt().receipt_id
    assert receipt.semantic_content_hash != _active_receipt().semantic_content_hash
    assert receipt.semantic_payload()["destination"] == destination.semantic_payload()


def test_external_destination_never_fabricates_internal_lot_identity() -> None:
    destination = LotDisposalDestination(
        destination_type=LotDisposalDestinationType.EXTERNAL_TRANSFER,
        external_destination_reference="  CUSTODIAN-ACCOUNT-7788  ",
    )

    assert destination.external_destination_reference == "CUSTODIAN-ACCOUNT-7788"
    assert destination.target_transaction_id is None
    assert destination.target_lot_id is None


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"target_transaction_id": None}, "complete target identity"),
        ({"target_lot_id": "LOT-WRONG"}, "must derive"),
        ({"external_destination_reference": "EXT"}, "cannot carry an external"),
    ],
)
def test_internal_destination_rejects_incomplete_or_mixed_identity(
    updates: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_internal_destination(), **updates)


def test_external_destination_requires_exactly_external_identity() -> None:
    with pytest.raises(ValueError, match="requires an external reference"):
        LotDisposalDestination(
            destination_type=LotDisposalDestinationType.EXTERNAL_TRANSFER,
        )
    with pytest.raises(ValueError, match="cannot carry internal target identity"):
        LotDisposalDestination(
            destination_type=LotDisposalDestinationType.EXTERNAL_TRANSFER,
            external_destination_reference="EXT-1",
            target_transaction_id="TRANSFER-IN-1",
        )


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
    receipt = _voided_receipt()

    assert receipt.semantic_payload()["status"] == "VOIDED"
    assert receipt.semantic_payload()["allocations"] == []
    assert receipt.semantic_content_hash != _active_receipt().semantic_content_hash


@pytest.mark.parametrize(
    ("updates", "exception", "message"),
    [
        ({"portfolio_id": 17}, TypeError, "portfolio_id must be a string"),
        ({"portfolio_id": "  "}, ValueError, "portfolio_id must be nonblank"),
        ({"disposal_timestamp": "2026-07-01"}, TypeError, "must be a datetime"),
        (
            {"disposal_timestamp": datetime(2026, 7, 1)},
            ValueError,
            "must be timezone-aware",
        ),
        ({"cost_basis_method": "FIFO"}, TypeError, "must be a CostBasisMethod"),
        ({"calculation_policy_id": 1}, TypeError, "must be a string or None"),
        (
            {"calculation_policy_id": None},
            ValueError,
            "ID and version must be supplied together",
        ),
        (
            {"transaction_calculation_lineage": None},
            TypeError,
            "must be a CalculationLineage",
        ),
        ({"status": "ACTIVE"}, TypeError, "must be a LotDisposalReceiptStatus"),
        ({"consumed_quantity": 1}, TypeError, "must be a Decimal"),
        (
            {"consumed_quantity": Decimal("NaN")},
            ValueError,
            "must be finite and non-negative",
        ),
        (
            {"consumed_cost_base": Decimal("-1")},
            ValueError,
            "must be finite and non-negative",
        ),
        ({"allocations": []}, TypeError, "allocations must be a tuple"),
        (
            {"consumed_quantity": Decimal(0), "allocations": ()},
            ValueError,
            "must carry positive allocations",
        ),
        (
            {"disposal_calculation_lineage": None},
            ValueError,
            "requires disposal calculation lineage",
        ),
        ({"void_reason": "NOT_VOID"}, ValueError, "cannot carry a void reason"),
    ],
)
def test_active_receipt_rejects_invalid_contract_shapes(
    updates: dict[str, object],
    exception: type[Exception],
    message: str,
) -> None:
    with pytest.raises(exception, match=message):
        replace(_active_receipt(), **updates)


def test_policy_identity_is_trimmed_as_one_atomic_pair() -> None:
    receipt = replace(
        _active_receipt(),
        calculation_policy_id="  fixed-income-book-cost  ",
        calculation_policy_version="  2  ",
    )

    assert receipt.calculation_policy_id == "fixed-income-book-cost"
    assert receipt.calculation_policy_version == "2"


def test_active_receipt_rejects_noncontiguous_or_duplicate_allocations() -> None:
    first = replace(
        _allocation(),
        consumed_quantity=Decimal("0.5"),
        consumed_cost_local=Decimal("5"),
        consumed_cost_base=Decimal("5"),
    )
    noncontiguous = replace(first, allocation_ordinal=2)
    duplicate = replace(
        first,
        allocation_ordinal=2,
        source_transaction_id="BUY-RECEIPT-02",
    )

    with pytest.raises(ValueError, match="ordinals must be contiguous"):
        replace(
            _active_receipt(),
            consumed_quantity=Decimal("0.5"),
            consumed_cost_local=Decimal("5"),
            consumed_cost_base=Decimal("5"),
            allocations=(noncontiguous,),
        )
    with pytest.raises(ValueError, match="source lots must be unique"):
        replace(
            _active_receipt(),
            allocations=(first, duplicate),
        )


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"consumed_quantity": Decimal("2")}, "quantity does not reconcile"),
        ({"consumed_cost_base": Decimal("11")}, "base cost does not reconcile"),
    ],
)
def test_active_receipt_rejects_nonconserved_totals(
    updates: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_active_receipt(), **updates)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"consumed_quantity": Decimal("1")}, "cannot carry economics or allocations"),
        (
            {"allocations": (_allocation(),)},
            "cannot carry economics or allocations",
        ),
        (
            {"disposal_calculation_lineage": _lineage("lot-disposal")},
            "cannot carry disposal lineage",
        ),
        ({"void_reason": "  "}, "requires a nonblank reason"),
        ({"void_reason": None}, "requires a nonblank reason"),
    ],
)
def test_voided_receipt_rejects_inconsistent_evidence(
    updates: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_voided_receipt(), **updates)


def test_void_reason_is_trimmed_before_hashing() -> None:
    receipt = replace(_voided_receipt(), void_reason="  DUPLICATE_REPLAY  ")

    assert receipt.void_reason == "DUPLICATE_REPLAY"
