from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.database_models import OutboxEvent, PositionHistory, PositionState
from sqlalchemy import func, select
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


async def test_backdated_transaction_rebuilds_current_epoch_without_legacy_replay_topic(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-COMBINED-BACKDATED-01"
    security_id = "SEC-COMBINED-BACKDATED-01"
    later_event = booked_transaction_event(
        transaction_id="BUY-COMBINED-LATER-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 1, 10, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="10",
        price="100",
        gross_amount="1000",
    )
    earlier_event = booked_transaction_event(
        transaction_id="BUY-COMBINED-EARLIER-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="5",
        price="80",
        gross_amount="400",
    )
    async_db_session.add_all(
        [
            portfolio_record(portfolio_id),
            instrument_record(
                security_id,
                name="Combined Backdated Equity",
                isin="SG0000000201",
                currency="USD",
            ),
        ]
    )
    await async_db_session.commit()
    context = transaction_processing_test_context(async_db_session)

    later_result = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=later_event,
        event_id="transactions.persisted-0-9201",
        correlation_id="corr-combined-backdated-01",
    )
    earlier_result = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=earlier_event,
        event_id="transactions.persisted-0-9202",
        correlation_id="corr-combined-backdated-01",
    )

    assert later_result.status is TransactionProcessingStatus.PROCESSED
    assert earlier_result.status is TransactionProcessingStatus.PROCESSED
    assert earlier_result.replay_queued_count == 0

    async with context.session_factory() as verification_session:
        state = (
            await verification_session.execute(
                select(PositionState).where(
                    PositionState.portfolio_id == portfolio_id,
                    PositionState.security_id == security_id,
                )
            )
        ).scalar_one()
        current_positions = (
            (
                await verification_session.execute(
                    select(PositionHistory)
                    .where(
                        PositionHistory.portfolio_id == portfolio_id,
                        PositionHistory.security_id == security_id,
                        PositionHistory.epoch == state.epoch,
                    )
                    .order_by(PositionHistory.position_date, PositionHistory.transaction_id)
                )
            )
            .scalars()
            .all()
        )
        legacy_replay_event_count = int(
            await verification_session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(
                    OutboxEvent.aggregate_id == portfolio_id,
                    OutboxEvent.event_type == "ReprocessTransactionReplay",
                )
            )
            or 0
        )

    assert state.epoch == 1
    assert [position.transaction_id for position in current_positions] == [
        "BUY-COMBINED-EARLIER-01",
        "BUY-COMBINED-LATER-01",
    ]
    assert [position.quantity for position in current_positions] == [
        Decimal("5"),
        Decimal("15"),
    ]
    assert [position.cost_basis for position in current_positions] == [
        Decimal("400"),
        Decimal("1400"),
    ]
    assert legacy_replay_event_count == 0
