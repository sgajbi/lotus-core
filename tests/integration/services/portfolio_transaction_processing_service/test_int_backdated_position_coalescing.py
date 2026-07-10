from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.database_models import OutboxEvent, PositionHistory, PositionState
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_support.transaction_processing import (
    booked_transaction_event,
    canonical_transaction_record,
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
    pytest.mark.resilience,
]


async def test_concurrent_backdated_triggers_coalesce_after_one_current_epoch_rebuild(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-BACKDATED-COALESCE-01"
    security_id = "SEC-BACKDATED-COALESCE-01"
    current_buy = booked_transaction_event(
        transaction_id="BUY-BACKDATED-COALESCE-03",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="10",
        price="10",
        gross_amount="100",
    )
    earliest_buy = booked_transaction_event(
        transaction_id="BUY-BACKDATED-COALESCE-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="5",
        price="10",
        gross_amount="50",
    )
    middle_buy = booked_transaction_event(
        transaction_id="BUY-BACKDATED-COALESCE-02",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 7, 2, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="3",
        price="10",
        gross_amount="30",
    )
    async_db_session.add_all(
        [
            portfolio_record(portfolio_id, cost_basis_method="FIFO"),
            instrument_record(
                security_id,
                name="Backdated Coalescing Proof Equity",
                isin="SG0000000486",
                currency="USD",
            ),
        ]
    )
    await async_db_session.commit()
    context = transaction_processing_test_context(async_db_session)
    await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=current_buy,
        event_id="transactions.persisted-0-4860",
        correlation_id="corr-backdated-coalesce-current",
    )

    async_db_session.add_all(
        [
            canonical_transaction_record(earliest_buy),
            canonical_transaction_record(middle_buy),
        ]
    )
    await async_db_session.commit()

    results = await asyncio.wait_for(
        asyncio.gather(
            process_booked_transaction(
                context=context,
                event=earliest_buy,
                event_id="transactions.persisted-0-4861",
                correlation_id="corr-backdated-coalesce-earliest",
            ),
            process_booked_transaction(
                context=context,
                event=middle_buy,
                event_id="transactions.persisted-0-4862",
                correlation_id="corr-backdated-coalesce-middle",
            ),
        ),
        timeout=10,
    )

    assert sorted(result.position_record_count for result in results) == [0, 3]
    assert all(result.replay_queued_count == 0 for result in results)

    async with context.session_factory() as verification_session:
        state = (
            await verification_session.scalars(
                select(PositionState).where(
                    PositionState.portfolio_id == portfolio_id,
                    PositionState.security_id == security_id,
                )
            )
        ).one()
        current_positions = list(
            (
                await verification_session.scalars(
                    select(PositionHistory)
                    .where(
                        PositionHistory.portfolio_id == portfolio_id,
                        PositionHistory.security_id == security_id,
                        PositionHistory.epoch == state.epoch,
                    )
                    .order_by(PositionHistory.position_date, PositionHistory.transaction_id)
                )
            ).all()
        )
        replay_event_count = await verification_session.scalar(
            select(func.count(OutboxEvent.id)).where(
                OutboxEvent.event_type == "ReprocessTransactionReplay",
            )
        )

    assert state.epoch == 1
    assert [position.transaction_id for position in current_positions] == [
        earliest_buy.transaction_id,
        middle_buy.transaction_id,
        current_buy.transaction_id,
    ]
    assert [position.quantity for position in current_positions] == [
        Decimal("5"),
        Decimal("8"),
        Decimal("18"),
    ]
    assert [position.cost_basis for position in current_positions] == [
        Decimal("50"),
        Decimal("80"),
        Decimal("180"),
    ]
    assert replay_event_count == 0
