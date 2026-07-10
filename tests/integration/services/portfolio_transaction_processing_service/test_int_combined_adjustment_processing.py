from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    Cashflow,
    OutboxEvent,
    Portfolio,
    PositionHistory,
    ProcessedEvent,
)
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.events import TransactionEvent
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.portfolio_transaction_processing_service.app.application import (
    TransactionProcessingStatus,
)
from src.services.portfolio_transaction_processing_service.app.delivery.kafka import (
    map_transaction_event,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    TRANSACTION_PROCESSING_SERVICE_NAME,
    build_process_transaction_use_case,
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
    async_db_session.add(
        Portfolio(
            portfolio_id=portfolio_id,
            base_currency="USD",
            open_date=date(2025, 1, 1),
            risk_exposure="MODERATE",
            investment_time_horizon="MEDIUM_TERM",
            portfolio_type="DISCRETIONARY",
            booking_center_code="SG",
            client_id="CLIENT-COMBINED-01",
            is_leverage_allowed=False,
            status="ACTIVE",
        )
    )
    async_db_session.add(
        DBTransaction(
            transaction_id=transaction_id,
            portfolio_id=portfolio_id,
            instrument_id="CASH",
            security_id="CASH",
            transaction_date=datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
            transaction_type="ADJUSTMENT",
            quantity=Decimal("0"),
            price=Decimal("0"),
            gross_transaction_amount=Decimal("125.50"),
            trade_currency="USD",
            currency="USD",
        )
    )
    await async_db_session.commit()
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    use_case = build_process_transaction_use_case(session_factory=session_factory)
    command = map_transaction_event(
        TransactionEvent(
            transaction_id=transaction_id,
            portfolio_id=portfolio_id,
            instrument_id="CASH",
            security_id="CASH",
            transaction_date=datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
            transaction_type="ADJUSTMENT",
            quantity=Decimal("0"),
            price=Decimal("0"),
            gross_transaction_amount=Decimal("125.50"),
            trade_currency="USD",
            currency="USD",
        ),
        event_id=event_id,
        correlation_id="corr-combined-adjustment-01",
    )

    result = await use_case.execute(command)
    duplicate_result = await use_case.execute(command)

    assert result.status is TransactionProcessingStatus.PROCESSED
    assert result.processed_transaction_ids == (transaction_id,)
    assert result.cashflow_record_count == 1
    assert result.position_record_count == 1
    assert duplicate_result.status is TransactionProcessingStatus.DUPLICATE

    async with session_factory() as verification_session:
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
