"""Prove an external securities transfer retains governed source-lot destination evidence."""

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
    transaction_processing_test_context,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.integration_db,
    pytest.mark.db_direct,
    pytest.mark.regression,
]


async def test_external_transfer_out_persists_opaque_destination_and_source_allocation(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-EXTERNAL-TRANSFER-01"
    security_id = "FO_EQ_EXTERNAL_TRANSFER_01"
    acquisition = booked_transaction_event(
        transaction_id="BUY-EXTERNAL-TRANSFER-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="100",
        price="10",
        gross_amount="1000",
    )
    transfer_out = booked_transaction_event(
        transaction_id="TRANSFER-OUT-EXTERNAL-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 7, 5, 10, 0, tzinfo=timezone.utc),
        transaction_type="TRANSFER_OUT",
        quantity="100",
        price="10",
        gross_amount="1000",
        external_destination_reference="CUSTODIAN-ACCOUNT-7788",
    )
    async_db_session.add(portfolio_record(portfolio_id, cost_basis_method="FIFO"))
    async_db_session.add(
        instrument_record(
            security_id,
            name="Externally Transferred Equity",
            isin="SG0000007788",
            currency="USD",
        )
    )
    context = transaction_processing_test_context(async_db_session)

    results = []
    for offset, event in enumerate((acquisition, transfer_out), start=9701):
        results.append(
            await persist_and_process_booked_transaction(
                session=async_db_session,
                context=context,
                event=event,
                event_id=f"transactions.persisted-0-{offset}",
                correlation_id=f"corr-{event.transaction_id.lower()}",
            )
        )

    assert all(result.status is TransactionProcessingStatus.PROCESSED for result in results)

    async with context.session_factory() as verification_session:
        persisted_transaction = (
            await verification_session.execute(
                select(DBTransaction).where(
                    DBTransaction.transaction_id == transfer_out.transaction_id
                )
            )
        ).scalar_one()
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
        source_lot = (
            await verification_session.execute(
                select(PositionLotState).where(
                    PositionLotState.portfolio_id == portfolio_id,
                    PositionLotState.source_transaction_id == acquisition.transaction_id,
                )
            )
        ).scalar_one()

    assert persisted_transaction.external_destination_reference == "CUSTODIAN-ACCOUNT-7788"
    assert persisted_transaction.realized_gain_loss is None
    assert receipt.destination_type == "EXTERNAL_TRANSFER"
    assert receipt.external_destination_reference == "CUSTODIAN-ACCOUNT-7788"
    assert receipt.target_transaction_id is None
    assert receipt.target_lot_id is None
    assert receipt.target_instrument_id is None
    assert [
        (
            allocation.source_transaction_id,
            allocation.consumed_quantity,
            allocation.consumed_cost_local,
            allocation.consumed_cost_base,
        )
        for allocation in allocations
    ] == [(acquisition.transaction_id, Decimal("100"), Decimal("1000"), Decimal("1000"))]
    assert source_lot.open_quantity == Decimal("0")
    assert source_lot.lot_cost_local == Decimal("0")
    assert source_lot.lot_cost_base == Decimal("0")
