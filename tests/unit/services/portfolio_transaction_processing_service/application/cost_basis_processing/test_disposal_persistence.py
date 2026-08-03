"""Verify disposal receipts use the exact cost-basis replay suffix."""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.services.portfolio_transaction_processing_service.app.application.cost_basis_processing.disposal_persistence import (  # noqa: E501
    persist_current_lot_disposals,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    CostBasisTransaction,
    LotDisposalResult,
    SourceLotDisposalAllocation,
    TransactionLotDisposal,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    CostBasisLotDisposalPort,
)


def _transaction(transaction_id: str, day: int) -> CostBasisTransaction:
    return CostBasisTransaction(
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
        repository=repository,
    )

    repository.reconcile_current_disposals.assert_awaited_once_with(
        affected_transaction_ids=(incoming.transaction_id, later.transaction_id),
        disposals=(
            _disposal(incoming.transaction_id, "LOT-2"),
            _disposal(later.transaction_id, "LOT-3"),
        ),
    )


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
            repository=repository,
        )

    repository.reconcile_current_disposals.assert_not_awaited()


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
            repository=repository,
        )

    repository.reconcile_current_disposals.assert_not_awaited()
