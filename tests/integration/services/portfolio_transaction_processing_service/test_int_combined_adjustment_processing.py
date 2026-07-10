from __future__ import annotations

from datetime import datetime, timezone

import pytest
from portfolio_common.database_models import (
    Cashflow,
    OutboxEvent,
    PositionHistory,
    ProcessedEvent,
)
from portfolio_common.database_models import Transaction as DBTransaction
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.application import (
    TransactionProcessingStatus,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    TRANSACTION_PROCESSING_SERVICE_NAME,
)
from tests.test_support.transaction_processing import (
    booked_transaction_event,
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


async def test_combined_adjustment_processing_persists_all_module_outputs_once(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-COMBINED-ADJUSTMENT-01"
    transaction_id = "ADJ-COMBINED-01"
    event_id = "transactions.persisted-0-9001"
    event = booked_transaction_event(
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        security_id="CASH",
        transaction_date=datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
        transaction_type="ADJUSTMENT",
        quantity="0",
        price="0",
        gross_amount="125.50",
    )
    async_db_session.add(portfolio_record(portfolio_id))
    context = transaction_processing_test_context(async_db_session)

    result = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=event,
        event_id=event_id,
        correlation_id="corr-combined-adjustment-01",
    )
    duplicate_result = await process_booked_transaction(
        context=context,
        event=event,
        event_id=event_id,
        correlation_id="corr-combined-adjustment-01",
    )

    assert result.status is TransactionProcessingStatus.PROCESSED
    assert result.processed_transaction_ids == (transaction_id,)
    assert result.cashflow_record_count == 1
    assert result.position_record_count == 1
    assert duplicate_result.status is TransactionProcessingStatus.DUPLICATE

    async with context.session_factory() as verification_session:
        assert (
            await _row_count(
                verification_session,
                select(func.count())
                .select_from(DBTransaction)
                .where(DBTransaction.transaction_id == transaction_id),
            )
            == 1
        )
        assert (
            await _row_count(
                verification_session,
                select(func.count())
                .select_from(Cashflow)
                .where(Cashflow.transaction_id == transaction_id),
            )
            == 1
        )
        assert (
            await _row_count(
                verification_session,
                select(func.count())
                .select_from(PositionHistory)
                .where(PositionHistory.transaction_id == transaction_id),
            )
            == 1
        )
        assert (
            await _row_count(
                verification_session,
                select(func.count())
                .select_from(ProcessedEvent)
                .where(
                    ProcessedEvent.event_id == event_id,
                    ProcessedEvent.service_name == TRANSACTION_PROCESSING_SERVICE_NAME,
                ),
            )
            == 1
        )
        outbox_event_types = (
            (
                await verification_session.execute(
                    select(OutboxEvent.event_type)
                    .where(OutboxEvent.aggregate_id == portfolio_id)
                    .order_by(OutboxEvent.event_type)
                )
            )
            .scalars()
            .all()
        )

    assert outbox_event_types == ["CashflowCalculated", "ProcessedTransactionPersisted"]


async def _row_count(session: AsyncSession, statement) -> int:
    return int(await session.scalar(statement) or 0)
