"""Verify disposal receipts use the exact cost-basis replay suffix."""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from portfolio_common.domain.calculation_lineage import build_calculation_lineage
from portfolio_common.domain.cost_basis_method import CostBasisMethod

from src.services.portfolio_transaction_processing_service.app.application.cost_basis_processing.disposal_persistence import (  # noqa: E501
    persist_current_lot_disposals,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    CostBasisTransaction,
    LotDisposalDestinationType,
    LotDisposalReceiptStatus,
    LotDisposalResult,
    SourceLotDisposalAllocation,
    TransactionLotDisposal,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    CostBasisLotDisposalPort,
)


def _transaction(transaction_id: str, day: int) -> CostBasisTransaction:
    transaction = CostBasisTransaction(
        transaction_id=transaction_id,
        portfolio_id="PORT-DISPOSAL-01",
        instrument_id="INSTRUMENT-DISPOSAL-01",
        security_id="SECURITY-DISPOSAL-01",
        transaction_date=datetime(2026, 7, day, tzinfo=timezone.utc),
        transaction_type="SELL",
        quantity=Decimal("1"),
        price=Decimal("10"),
        gross_transaction_amount=Decimal("10"),
        trade_currency="SGD",
        currency="SGD",
        portfolio_base_currency="SGD",
        transaction_fx_rate=Decimal("1"),
    )
    transaction.set_calculated_field(
        "calculation_lineage",
        build_calculation_lineage(
            algorithm_id="test-transaction-cost",
            algorithm_version=1,
            intermediate_precision=38,
            input_payload={"transaction_id": transaction_id},
            output_payload={"net_cost": Decimal("10")},
        ),
    )
    return transaction


def _disposal(transaction_id: str, source_lot_id: str) -> TransactionLotDisposal:
    return TransactionLotDisposal(
        disposal_transaction_id=transaction_id,
        result=LotDisposalResult(
            cost_base=Decimal("10"),
            cost_local=Decimal("10"),
            consumed_quantity=Decimal("1"),
            allocations=(
                SourceLotDisposalAllocation(
                    source_lot_id=source_lot_id,
                    source_transaction_id=f"SOURCE-{source_lot_id}",
                    source_acquisition_date=date(2026, 1, 1),
                    allocation_ordinal=1,
                    consumed_quantity=Decimal("1"),
                    consumed_cost_local=Decimal("10"),
                    consumed_cost_base=Decimal("10"),
                ),
            ),
        ),
    )


@pytest.mark.asyncio
async def test_persistence_reconciles_only_disposals_in_affected_suffix() -> None:
    earlier = _transaction("SELL-EARLIER", 1)
    incoming = _transaction("SELL-INCOMING", 2)
    later = _transaction("SELL-LATER", 3)
    repository = AsyncMock(spec=CostBasisLotDisposalPort)

    await persist_current_lot_disposals(
        processed=[earlier, incoming, later],
        incoming_transaction_ids={incoming.transaction_id},
        disposals=[
            _disposal(earlier.transaction_id, "LOT-1"),
            _disposal(incoming.transaction_id, "LOT-2"),
            _disposal(later.transaction_id, "LOT-3"),
        ],
        cost_basis_method=CostBasisMethod.FIFO,
        repository=repository,
    )

    receipt_states = repository.reconcile_disposal_receipts.await_args.kwargs["receipt_states"]
    assert tuple(state.disposal_transaction_id for state in receipt_states) == (
        incoming.transaction_id,
        later.transaction_id,
    )
    assert tuple(state.status for state in receipt_states) == (
        LotDisposalReceiptStatus.ACTIVE,
        LotDisposalReceiptStatus.ACTIVE,
    )
    assert tuple(state.allocations[0].source_lot_id for state in receipt_states) == (
        "LOT-2",
        "LOT-3",
    )


@pytest.mark.asyncio
async def test_persistence_emits_explicit_void_state_when_disposal_is_absent() -> None:
    incoming = _transaction("BUY-INCOMING", 2)
    incoming.transaction_type = "BUY"
    repository = AsyncMock(spec=CostBasisLotDisposalPort)

    await persist_current_lot_disposals(
        processed=[incoming],
        incoming_transaction_ids={incoming.transaction_id},
        disposals=[],
        cost_basis_method=CostBasisMethod.AVCO,
        repository=repository,
    )

    (state,) = repository.reconcile_disposal_receipts.await_args.kwargs["receipt_states"]
    assert state.status is LotDisposalReceiptStatus.VOIDED
    assert state.void_reason == "RECALCULATED_WITHOUT_LOT_DISPOSAL"
    assert state.allocations == ()
    assert state.cost_basis_method is CostBasisMethod.AVCO


@pytest.mark.asyncio
@pytest.mark.parametrize("transaction_type", ("EXCHANGE_OUT", "MERGER_OUT", "REPLACEMENT_OUT"))
async def test_persistence_records_internal_target_lot_destination(
    transaction_type: str,
) -> None:
    outgoing = _transaction(f"{transaction_type}-01", 2)
    outgoing.transaction_type = transaction_type
    outgoing.target_instrument_id = "TARGET-INSTRUMENT-01"
    outgoing.target_transaction_reference = "TARGET-TRANSACTION-01"
    repository = AsyncMock(spec=CostBasisLotDisposalPort)

    await persist_current_lot_disposals(
        processed=[outgoing],
        incoming_transaction_ids={outgoing.transaction_id},
        disposals=[_disposal(outgoing.transaction_id, "SOURCE-LOT-01")],
        cost_basis_method=CostBasisMethod.FIFO,
        repository=repository,
    )

    (state,) = repository.reconcile_disposal_receipts.await_args.kwargs["receipt_states"]
    assert state.destination is not None
    assert state.destination.destination_type is LotDisposalDestinationType.INTERNAL_LOT
    assert state.destination.target_transaction_id == "TARGET-TRANSACTION-01"
    assert state.destination.target_lot_id == "LOT-TARGET-TRANSACTION-01"
    assert state.destination.target_instrument_id == "TARGET-INSTRUMENT-01"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("target_transaction_reference", "target_instrument_id", "missing_field"),
    (
        (None, "TARGET-INSTRUMENT-01", "target_transaction_reference"),
        ("TARGET-TRANSACTION-01", None, "target_instrument_id"),
    ),
)
async def test_internal_lot_disposal_fails_closed_without_target_identity(
    target_transaction_reference: str | None,
    target_instrument_id: str | None,
    missing_field: str,
) -> None:
    outgoing = _transaction("EXCHANGE-OUT-01", 2)
    outgoing.transaction_type = "EXCHANGE_OUT"
    outgoing.target_transaction_reference = target_transaction_reference
    outgoing.target_instrument_id = target_instrument_id
    repository = AsyncMock(spec=CostBasisLotDisposalPort)

    with pytest.raises(ValueError, match=missing_field):
        await persist_current_lot_disposals(
            processed=[outgoing],
            incoming_transaction_ids={outgoing.transaction_id},
            disposals=[_disposal(outgoing.transaction_id, "SOURCE-LOT-01")],
            cost_basis_method=CostBasisMethod.FIFO,
            repository=repository,
        )

    repository.reconcile_disposal_receipts.assert_not_awaited()


@pytest.mark.asyncio
async def test_transfer_out_records_governed_external_destination_without_internal_identity(
) -> None:
    outgoing = _transaction("TRANSFER-OUT-EXTERNAL-01", 2)
    outgoing.transaction_type = "TRANSFER_OUT"
    outgoing.external_destination_reference = "  CUSTODIAN-ACCOUNT-7788  "
    repository = AsyncMock(spec=CostBasisLotDisposalPort)

    await persist_current_lot_disposals(
        processed=[outgoing],
        incoming_transaction_ids={outgoing.transaction_id},
        disposals=[_disposal(outgoing.transaction_id, "SOURCE-LOT-01")],
        cost_basis_method=CostBasisMethod.FIFO,
        repository=repository,
    )

    (state,) = repository.reconcile_disposal_receipts.await_args.kwargs["receipt_states"]
    assert state.destination is not None
    assert state.destination.destination_type is LotDisposalDestinationType.EXTERNAL_TRANSFER
    assert state.destination.external_destination_reference == "CUSTODIAN-ACCOUNT-7788"
    assert state.destination.target_transaction_id is None
    assert state.destination.target_lot_id is None
    assert state.destination.target_instrument_id is None


@pytest.mark.asyncio
async def test_transfer_out_records_explicit_internal_destination() -> None:
    outgoing = _transaction("TRANSFER-OUT-INTERNAL-01", 2)
    outgoing.transaction_type = "TRANSFER_OUT"
    outgoing.target_transaction_reference = "TRANSFER-IN-INTERNAL-01"
    outgoing.target_instrument_id = "INSTRUMENT-DISPOSAL-01"
    repository = AsyncMock(spec=CostBasisLotDisposalPort)

    await persist_current_lot_disposals(
        processed=[outgoing],
        incoming_transaction_ids={outgoing.transaction_id},
        disposals=[_disposal(outgoing.transaction_id, "SOURCE-LOT-01")],
        cost_basis_method=CostBasisMethod.FIFO,
        repository=repository,
    )

    (state,) = repository.reconcile_disposal_receipts.await_args.kwargs["receipt_states"]
    assert state.destination is not None
    assert state.destination.destination_type is LotDisposalDestinationType.INTERNAL_LOT
    assert state.destination.target_transaction_id == "TRANSFER-IN-INTERNAL-01"
    assert state.destination.target_lot_id == "LOT-TRANSFER-IN-INTERNAL-01"


@pytest.mark.asyncio
async def test_transfer_out_fails_closed_for_partial_internal_destination() -> None:
    outgoing = _transaction("TRANSFER-OUT-PARTIAL-01", 2)
    outgoing.transaction_type = "TRANSFER_OUT"
    outgoing.target_transaction_reference = "TRANSFER-IN-PARTIAL-01"
    outgoing.target_instrument_id = None
    repository = AsyncMock(spec=CostBasisLotDisposalPort)

    with pytest.raises(ValueError, match="target_instrument_id"):
        await persist_current_lot_disposals(
            processed=[outgoing],
            incoming_transaction_ids={outgoing.transaction_id},
            disposals=[_disposal(outgoing.transaction_id, "SOURCE-LOT-01")],
            cost_basis_method=CostBasisMethod.FIFO,
            repository=repository,
        )

    repository.reconcile_disposal_receipts.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("transaction_type", "target_transaction_reference", "target_instrument_id", "error"),
    (
        ("TRANSFER_OUT", "TRANSFER-IN-01", "INSTRUMENT-02", "exactly one"),
        ("TRANSFER_OUT", "TRANSFER-IN-01", None, "exactly one"),
        ("SELL", None, None, "valid only for TRANSFER_OUT"),
        ("EXCHANGE_OUT", "EXCHANGE-IN-01", "INSTRUMENT-02", "internal lot destination"),
    ),
)
async def test_external_destination_authority_fails_closed_for_ambiguous_or_invalid_shape(
    transaction_type: str,
    target_transaction_reference: str | None,
    target_instrument_id: str | None,
    error: str,
) -> None:
    outgoing = _transaction(f"{transaction_type}-DESTINATION-01", 2)
    outgoing.transaction_type = transaction_type
    outgoing.target_transaction_reference = target_transaction_reference
    outgoing.target_instrument_id = target_instrument_id
    outgoing.external_destination_reference = "CUSTODIAN-ACCOUNT-7788"
    repository = AsyncMock(spec=CostBasisLotDisposalPort)

    with pytest.raises(ValueError, match=error):
        await persist_current_lot_disposals(
            processed=[outgoing],
            incoming_transaction_ids={outgoing.transaction_id},
            disposals=[_disposal(outgoing.transaction_id, "SOURCE-LOT-01")],
            cost_basis_method=CostBasisMethod.FIFO,
            repository=repository,
        )

    repository.reconcile_disposal_receipts.assert_not_awaited()


@pytest.mark.asyncio
async def test_persistence_fails_closed_for_duplicate_disposal_evidence() -> None:
    incoming = _transaction("SELL-INCOMING", 2)
    disposal = _disposal(incoming.transaction_id, "LOT-2")
    repository = AsyncMock(spec=CostBasisLotDisposalPort)

    with pytest.raises(
        ValueError,
        match="Calculated timeline emitted duplicate lot-disposal evidence",
    ):
        await persist_current_lot_disposals(
            processed=[incoming],
            incoming_transaction_ids={incoming.transaction_id},
            disposals=[disposal, disposal],
            cost_basis_method=CostBasisMethod.FIFO,
            repository=repository,
        )

    repository.reconcile_disposal_receipts.assert_not_awaited()


@pytest.mark.asyncio
async def test_persistence_fails_closed_for_disposal_outside_timeline() -> None:
    incoming = _transaction("SELL-INCOMING", 2)
    repository = AsyncMock(spec=CostBasisLotDisposalPort)

    with pytest.raises(
        ValueError,
        match="Lot-disposal evidence references a transaction outside the calculated timeline",
    ):
        await persist_current_lot_disposals(
            processed=[incoming],
            incoming_transaction_ids={incoming.transaction_id},
            disposals=[_disposal("SELL-UNKNOWN", "LOT-9")],
            cost_basis_method=CostBasisMethod.FIFO,
            repository=repository,
        )

    repository.reconcile_disposal_receipts.assert_not_awaited()
