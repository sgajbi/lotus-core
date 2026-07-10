from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    FxRate,
    OutboxEvent,
    PositionHistory,
    PositionLotState,
    PositionState,
    TransactionCost,
)
from portfolio_common.database_models import Transaction as DBTransaction
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

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


async def _process_events(
    *,
    session: AsyncSession,
    context,
    events,
    offset: int,
    correlation_id: str,
) -> None:
    for event_offset, event in enumerate(events, start=offset):
        await persist_and_process_booked_transaction(
            session=session,
            context=context,
            event=event,
            event_id=f"transactions.persisted-0-{event_offset}",
            correlation_id=correlation_id,
        )


async def _current_position_rows(
    *,
    session: AsyncSession,
    portfolio_id: str,
    security_id: str,
) -> list[PositionHistory]:
    epoch = await session.scalar(
        select(PositionState.epoch).where(
            PositionState.portfolio_id == portfolio_id,
            PositionState.security_id == security_id,
        )
    )
    return list(
        (
            await session.execute(
                select(PositionHistory)
                .where(
                    PositionHistory.portfolio_id == portfolio_id,
                    PositionHistory.security_id == security_id,
                    PositionHistory.epoch == epoch,
                )
                .order_by(PositionHistory.position_date, PositionHistory.transaction_id)
            )
        )
        .scalars()
        .all()
    )


async def test_backdated_fee_buy_corrects_later_fifo_multi_lot_disposal(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-COMBINED-BACKDATED-FEE-MULTI-01"
    security_id = "SEC-COMBINED-BACKDATED-FEE-MULTI-01"
    later_buy_one = booked_transaction_event(
        transaction_id="BUY-BACKDATED-FEE-LATER-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 3, 5, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="100",
        price="10",
        gross_amount="1000",
        trade_fee="10",
    )
    later_buy_two = booked_transaction_event(
        transaction_id="BUY-BACKDATED-FEE-LATER-02",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 3, 7, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="50",
        price="12",
        gross_amount="600",
        trade_fee="5",
    )
    later_sell = booked_transaction_event(
        transaction_id="SELL-BACKDATED-FEE-LATER-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc),
        transaction_type="SELL",
        quantity="120",
        price="15",
        gross_amount="1800",
        trade_fee="6",
    )
    earlier_buy = booked_transaction_event(
        transaction_id="BUY-BACKDATED-FEE-EARLIER-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="50",
        price="8",
        gross_amount="400",
        trade_fee="4",
    )
    async_db_session.add_all(
        [
            portfolio_record(portfolio_id, cost_basis_method="FIFO"),
            instrument_record(
                security_id,
                name="Backdated Fee Multi Lot Equity",
                isin="SG0000000204",
                currency="USD",
            ),
        ]
    )
    await async_db_session.commit()
    context = transaction_processing_test_context(async_db_session)
    await _process_events(
        session=async_db_session,
        context=context,
        events=(later_buy_one, later_buy_two, later_sell),
        offset=9501,
        correlation_id="corr-backdated-fee-multi-01",
    )

    result = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=earlier_buy,
        event_id="transactions.persisted-0-9504",
        correlation_id="corr-backdated-fee-multi-01",
    )

    async with context.session_factory() as verification_session:
        persisted_sell = (
            await verification_session.execute(
                select(DBTransaction).where(
                    DBTransaction.transaction_id == later_sell.transaction_id
                )
            )
        ).scalar_one()
        source_lots = (
            (
                await verification_session.execute(
                    select(PositionLotState)
                    .where(PositionLotState.portfolio_id == portfolio_id)
                    .order_by(PositionLotState.acquisition_date)
                )
            )
            .scalars()
            .all()
        )
        current_positions = await _current_position_rows(
            session=verification_session,
            portfolio_id=portfolio_id,
            security_id=security_id,
        )
        transaction_cost_count = int(
            await verification_session.scalar(select(func.count()).select_from(TransactionCost))
            or 0
        )
        processed_event_count = int(
            await verification_session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(
                    OutboxEvent.aggregate_id == portfolio_id,
                    OutboxEvent.event_type == "ProcessedTransactionPersisted",
                )
            )
            or 0
        )

    assert result.processed_transaction_ids == (earlier_buy.transaction_id,)
    assert persisted_sell.net_cost == Decimal("-1111")
    assert persisted_sell.realized_gain_loss == Decimal("683")
    assert [
        (lot.source_transaction_id, lot.open_quantity, lot.lot_cost_base) for lot in source_lots
    ] == [
        (earlier_buy.transaction_id, Decimal("0"), Decimal("0")),
        (later_buy_one.transaction_id, Decimal("30"), Decimal("303")),
        (later_buy_two.transaction_id, Decimal("50"), Decimal("605")),
    ]
    assert (current_positions[-1].quantity, current_positions[-1].cost_basis) == (
        Decimal("80"),
        Decimal("908"),
    )
    assert transaction_cost_count == 4
    assert processed_event_count == 4


async def test_backdated_cross_currency_buy_corrects_later_local_and_base_disposal(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-COMBINED-BACKDATED-FX-01"
    security_id = "SEC-COMBINED-BACKDATED-FX-01"
    later_buy = booked_transaction_event(
        transaction_id="BUY-BACKDATED-FX-LATER-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 4, 5, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="100",
        price="10",
        gross_amount="1000",
        trade_fee="10",
        trade_currency="EUR",
    )
    later_sell = booked_transaction_event(
        transaction_id="SELL-BACKDATED-FX-LATER-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc),
        transaction_type="SELL",
        quantity="100",
        price="12",
        gross_amount="1200",
        trade_fee="6",
        trade_currency="EUR",
    )
    earlier_buy = booked_transaction_event(
        transaction_id="BUY-BACKDATED-FX-EARLIER-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="100",
        price="8",
        gross_amount="800",
        trade_fee="8",
        trade_currency="EUR",
    )
    async_db_session.add_all(
        [
            portfolio_record(
                portfolio_id,
                base_currency="SGD",
                cost_basis_method="FIFO",
            ),
            instrument_record(
                security_id,
                name="Backdated Cross Currency Equity",
                isin="SG0000000205",
                currency="EUR",
            ),
            FxRate(
                from_currency="EUR",
                to_currency="SGD",
                rate_date=date(2026, 4, 1),
                rate=Decimal("1.40"),
            ),
            FxRate(
                from_currency="EUR",
                to_currency="SGD",
                rate_date=date(2026, 4, 5),
                rate=Decimal("1.50"),
            ),
            FxRate(
                from_currency="EUR",
                to_currency="SGD",
                rate_date=date(2026, 4, 10),
                rate=Decimal("1.60"),
            ),
        ]
    )
    await async_db_session.commit()
    context = transaction_processing_test_context(async_db_session)
    await _process_events(
        session=async_db_session,
        context=context,
        events=(later_buy, later_sell),
        offset=9601,
        correlation_id="corr-backdated-fx-01",
    )

    result = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=earlier_buy,
        event_id="transactions.persisted-0-9603",
        correlation_id="corr-backdated-fx-01",
    )

    async with context.session_factory() as verification_session:
        persisted_sell = (
            await verification_session.execute(
                select(DBTransaction).where(
                    DBTransaction.transaction_id == later_sell.transaction_id
                )
            )
        ).scalar_one()
        source_lots = (
            (
                await verification_session.execute(
                    select(PositionLotState)
                    .where(PositionLotState.portfolio_id == portfolio_id)
                    .order_by(PositionLotState.acquisition_date)
                )
            )
            .scalars()
            .all()
        )
        current_positions = await _current_position_rows(
            session=verification_session,
            portfolio_id=portfolio_id,
            security_id=security_id,
        )
        processed_event_count = int(
            await verification_session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(
                    OutboxEvent.aggregate_id == portfolio_id,
                    OutboxEvent.event_type == "ProcessedTransactionPersisted",
                )
            )
            or 0
        )

    assert result.processed_transaction_ids == (earlier_buy.transaction_id,)
    assert persisted_sell.transaction_fx_rate == Decimal("1.60")
    assert persisted_sell.net_cost_local == Decimal("-808")
    assert persisted_sell.net_cost == Decimal("-1131.20")
    assert persisted_sell.realized_gain_loss_local == Decimal("386")
    assert persisted_sell.realized_gain_loss == Decimal("779.20")
    assert [
        (
            lot.source_transaction_id,
            lot.open_quantity,
            lot.lot_cost_local,
            lot.lot_cost_base,
        )
        for lot in source_lots
    ] == [
        (earlier_buy.transaction_id, Decimal("0"), Decimal("0"), Decimal("0")),
        (
            later_buy.transaction_id,
            Decimal("100"),
            Decimal("1010"),
            Decimal("1515"),
        ),
    ]
    assert (
        current_positions[-1].quantity,
        current_positions[-1].cost_basis_local,
        current_positions[-1].cost_basis,
    ) == (Decimal("100"), Decimal("1010"), Decimal("1515"))
    assert processed_event_count == 3
