"""Verify basis-transfer receipts use the exact cost-basis replay suffix."""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from portfolio_common.domain.calculation_lineage import build_calculation_lineage
from portfolio_common.domain.cost_basis_method import CostBasisMethod

from src.services.portfolio_transaction_processing_service.app.application.cost_basis_processing.basis_transfer_persistence import (  # noqa: E501
    persist_current_lot_basis_transfers,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    CostBasisTransaction,
    LotBasisTransferResult,
    SourceLotBasisTransferAllocation,
    TransactionLotBasisTransfer,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    CostBasisLotBasisTransferPort,
)


def _transaction(transaction_id: str, day: int, *, security: str) -> CostBasisTransaction:
    transaction = CostBasisTransaction(
        transaction_id=transaction_id,
        portfolio_id="PORT-01",
        instrument_id=f"INSTRUMENT-{security}",
        security_id=security,
        transaction_date=datetime(2026, 7, day, tzinfo=timezone.utc),
        transaction_type="SPIN_OFF" if "OUT" in transaction_id else "SPIN_OFF_IN",
        quantity=Decimal(0),
        gross_transaction_amount=Decimal(0),
        trade_currency="SGD",
        portfolio_base_currency="SGD",
    )
    transaction.set_calculated_field(
        "calculation_lineage",
        build_calculation_lineage(
            algorithm_id="test-transaction-cost",
            algorithm_version=1,
            intermediate_precision=38,
            input_payload={"transaction_id": transaction_id},
            output_payload={"net_cost": Decimal(0)},
        ),
    )
    return transaction


def _transfer(source_id: str, target_id: str) -> TransactionLotBasisTransfer:
    return TransactionLotBasisTransfer(
        source_transaction_id=source_id,
        target_transaction_id=target_id,
        target_lot_id=f"LOT-{target_id}",
        result=LotBasisTransferResult(
            transferred_cost_local=Decimal("25"),
            transferred_cost_base=Decimal("30"),
            allocations=(
                SourceLotBasisTransferAllocation(
                    allocation_ordinal=1,
                    source_lot_id="LOT-BUY-01",
                    source_transaction_id="BUY-01",
                    source_acquisition_date=date(2026, 1, 1),
                    retained_quantity=Decimal("10"),
                    source_cost_local_before=Decimal("100"),
                    source_cost_base_before=Decimal("120"),
                    transferred_cost_local=Decimal("25"),
                    transferred_cost_base=Decimal("30"),
                    retained_cost_local=Decimal("75"),
                    retained_cost_base=Decimal("90"),
                ),
            ),
        ),
    )


@pytest.mark.asyncio
async def test_persistence_retains_source_scope_and_unmaterialized_target_reference() -> None:
    source = _transaction("SPIN-OFF-OUT-01", 2, security="SOURCE")
    source.target_instrument_id = "TARGET-INSTRUMENT"
    repository = AsyncMock(spec=CostBasisLotBasisTransferPort)

    await persist_current_lot_basis_transfers(
        processed=[source],
        incoming_transaction_ids={source.transaction_id},
        basis_transfers=[_transfer(source.transaction_id, "SPIN-OFF-IN-01")],
        cost_basis_method=CostBasisMethod.FIFO,
        repository=repository,
    )

    call = repository.reconcile_basis_transfer_receipts.await_args.kwargs
    assert tuple(scope.source_transaction_id for scope in call["reconciliation_scopes"]) == (
        source.transaction_id,
    )
    (state,) = call["receipt_states"]
    assert state.source_security_id == "SOURCE"
    assert state.target_instrument_id == "TARGET-INSTRUMENT"
    assert state.target_lot_id == "LOT-SPIN-OFF-IN-01"
    assert state.transferred_cost_local == Decimal("25")


@pytest.mark.asyncio
async def test_persistence_passes_empty_current_state_so_repository_can_void_prior_evidence() -> (
    None
):
    source = _transaction("SPIN-OFF-OUT-01", 2, security="SOURCE")
    repository = AsyncMock(spec=CostBasisLotBasisTransferPort)

    await persist_current_lot_basis_transfers(
        processed=[source],
        incoming_transaction_ids={source.transaction_id},
        basis_transfers=[],
        cost_basis_method=CostBasisMethod.FIFO,
        repository=repository,
    )

    call = repository.reconcile_basis_transfer_receipts.await_args.kwargs
    assert call["receipt_states"] == ()
    (scope,) = call["reconciliation_scopes"]
    assert scope.source_transaction_id == source.transaction_id
    assert scope.transaction_calculation_lineage == source.calculation_lineage


@pytest.mark.asyncio
async def test_persistence_rejects_source_identity_outside_timeline() -> None:
    source = _transaction("SPIN-OFF-OUT-01", 2, security="SOURCE")
    target = _transaction("SPIN-OFF-IN-01", 2, security="TARGET")
    processed = [target]
    repository = AsyncMock(spec=CostBasisLotBasisTransferPort)

    with pytest.raises(ValueError, match="source outside the calculated timeline"):
        await persist_current_lot_basis_transfers(
            processed=processed,
            incoming_transaction_ids={processed[0].transaction_id},
            basis_transfers=[_transfer(source.transaction_id, target.transaction_id)],
            cost_basis_method=CostBasisMethod.FIFO,
            repository=repository,
        )

    repository.reconcile_basis_transfer_receipts.assert_not_awaited()


@pytest.mark.asyncio
async def test_persistence_rejects_duplicate_source_evidence() -> None:
    source = _transaction("SPIN-OFF-OUT-01", 2, security="SOURCE")
    target = _transaction("SPIN-OFF-IN-01", 2, security="TARGET")
    transfer = _transfer(source.transaction_id, target.transaction_id)
    repository = AsyncMock(spec=CostBasisLotBasisTransferPort)

    with pytest.raises(ValueError, match="duplicate basis-transfer evidence"):
        await persist_current_lot_basis_transfers(
            processed=[source, target],
            incoming_transaction_ids={source.transaction_id},
            basis_transfers=[transfer, transfer],
            cost_basis_method=CostBasisMethod.FIFO,
            repository=repository,
        )

    repository.reconcile_basis_transfer_receipts.assert_not_awaited()
