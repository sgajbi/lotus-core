"""Prove partial internal transfers preserve basis and reciprocal lot lineage."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    LotDisposalAllocationRecord,
    LotDisposalReceiptRecord,
    PositionLotState,
)
from portfolio_common.database_models import Transaction as DBTransaction
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.application import (
    TransactionProcessingStatus,
)
from tests.test_support.transaction_processing import (
    booked_transaction_event,
    instrument_record,
    persist_and_process_booked_transaction,
    portfolio_record,
    process_booked_transaction,
    transaction_processing_test_context,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.integration_db,
    pytest.mark.db_direct,
    pytest.mark.regression,
]


async def test_partial_internal_transfer_preserves_basis_and_reciprocal_lot_lineage(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    source_portfolio_id = "PORT-PARTIAL-TRANSFER-SOURCE-01"
    target_portfolio_id = "PORT-PARTIAL-TRANSFER-TARGET-01"
    security_id = "FO_EQ_PARTIAL_TRANSFER_01"
    economic_event_id = "EVT-PARTIAL-TRANSFER-01"
    linked_group_id = "GROUP-PARTIAL-TRANSFER-01"

    acquisition = booked_transaction_event(
        transaction_id="BUY-PARTIAL-TRANSFER-01",
        portfolio_id=source_portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="100",
        price="10",
        gross_amount="1000",
    )
    transfer_out = booked_transaction_event(
        transaction_id="TRANSFER-OUT-PARTIAL-INTERNAL-01",
        portfolio_id=source_portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 7, 5, 10, 0, tzinfo=timezone.utc),
        transaction_type="TRANSFER_OUT",
        quantity="40",
        price="10",
        gross_amount="400",
        economic_event_id=economic_event_id,
        linked_transaction_group_id=linked_group_id,
        source_instrument_id=security_id,
        target_instrument_id=security_id,
        target_transaction_reference="TRANSFER-IN-PARTIAL-INTERNAL-01",
    )
    transfer_in = booked_transaction_event(
        transaction_id="TRANSFER-IN-PARTIAL-INTERNAL-01",
        portfolio_id=target_portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 7, 5, 10, 0, tzinfo=timezone.utc),
        transaction_type="TRANSFER_IN",
        quantity="40",
        price="10",
        gross_amount="400",
        economic_event_id=economic_event_id,
        linked_transaction_group_id=linked_group_id,
        source_instrument_id=security_id,
        target_instrument_id=security_id,
        source_transaction_reference=transfer_out.transaction_id,
    )

    async_db_session.add_all(
        [
            portfolio_record(source_portfolio_id, cost_basis_method="FIFO"),
            portfolio_record(target_portfolio_id, cost_basis_method="FIFO"),
            instrument_record(
                security_id,
                name="Partially Transferred Equity",
                isin="SG0000007796",
                currency="USD",
            ),
        ]
    )
    context = transaction_processing_test_context(async_db_session)

    results = []
    for offset, event in enumerate((acquisition, transfer_out, transfer_in), start=9801):
        results.append(
            await persist_and_process_booked_transaction(
                session=async_db_session,
                context=context,
                event=event,
                event_id=f"transactions.persisted-0-{offset}",
                correlation_id=f"corr-{event.transaction_id.lower()}",
            )
        )
    duplicate = await process_booked_transaction(
        context=context,
        event=transfer_in,
        event_id="transactions.persisted-0-9803",
        correlation_id="corr-transfer-in-partial-internal-01",
    )

    assert all(result.status is TransactionProcessingStatus.PROCESSED for result in results)
    assert duplicate.status is TransactionProcessingStatus.DUPLICATE

    async with context.session_factory() as verification_session:
        transactions = (
            (
                await verification_session.execute(
                    select(DBTransaction).where(
                        DBTransaction.transaction_id.in_(
                            [transfer_out.transaction_id, transfer_in.transaction_id]
                        )
                    )
                )
            )
            .scalars()
            .all()
        )
        lots = (
            (
                await verification_session.execute(
                    select(PositionLotState)
                    .where(PositionLotState.security_id == security_id)
                    .order_by(
                        PositionLotState.portfolio_id,
                        PositionLotState.source_transaction_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        receipt = (
            await verification_session.execute(
                select(LotDisposalReceiptRecord).where(
                    LotDisposalReceiptRecord.disposal_transaction_id == transfer_out.transaction_id
                )
            )
        ).scalar_one()
        allocations = (
            (
                await verification_session.execute(
                    select(LotDisposalAllocationRecord)
                    .where(
                        LotDisposalAllocationRecord.receipt_id == receipt.receipt_id,
                        LotDisposalAllocationRecord.receipt_version == receipt.receipt_version,
                    )
                    .order_by(LotDisposalAllocationRecord.allocation_ordinal)
                )
            )
            .scalars()
            .all()
        )

    transaction_by_id = {transaction.transaction_id: transaction for transaction in transactions}
    assert transaction_by_id[transfer_out.transaction_id].net_cost == Decimal("-400")
    assert transaction_by_id[transfer_in.transaction_id].net_cost == Decimal("400")
    assert all(transaction.realized_gain_loss is None for transaction in transactions)
    assert all(transaction.realized_fx_pnl_local is None for transaction in transactions)
    assert all(transaction.realized_fx_pnl_base is None for transaction in transactions)
    assert all(
        transaction.economic_event_id == economic_event_id
        and transaction.linked_transaction_group_id == linked_group_id
        for transaction in transactions
    )
    assert [
        (
            lot.portfolio_id,
            lot.source_transaction_id,
            lot.open_quantity,
            lot.lot_cost_local,
            lot.lot_cost_base,
        )
        for lot in lots
    ] == [
        (
            source_portfolio_id,
            acquisition.transaction_id,
            Decimal("60"),
            Decimal("600"),
            Decimal("600"),
        ),
        (
            target_portfolio_id,
            transfer_in.transaction_id,
            Decimal("40"),
            Decimal("400"),
            Decimal("400"),
        ),
    ]
    assert sum(lot.open_quantity for lot in lots) == Decimal("100")
    assert sum(lot.lot_cost_base for lot in lots) == Decimal("1000")
    assert receipt.destination_type == "INTERNAL_LOT"
    assert receipt.target_transaction_id == transfer_in.transaction_id
    assert receipt.target_lot_id == f"LOT-{transfer_in.transaction_id}"
    assert receipt.target_instrument_id == security_id
    assert receipt.external_destination_reference is None
    assert [
        (
            allocation.source_transaction_id,
            allocation.consumed_quantity,
            allocation.consumed_cost_local,
            allocation.consumed_cost_base,
        )
        for allocation in allocations
    ] == [(acquisition.transaction_id, Decimal("40"), Decimal("400"), Decimal("400"))]
