from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    AverageCostPoolState,
    PositionLotState,
)
from portfolio_common.domain.cost_basis_method import CostBasisMethod
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.application import (
    TransactionProcessingStatus,
)
from src.services.portfolio_transaction_processing_service.app.application.cost_basis_processing.timeline import (  # noqa: E501
    build_cost_basis_timeline_processor,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    CostBasisProcessingCheckpoint,
    build_cost_basis_engine_input,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    CostBasisTransaction as EngineTransaction,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    SqlAlchemyAverageCostPoolRepository,
    SqlAlchemyCostBasisProcessingStateRepository,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_mapping import (  # noqa: E501
    booked_transaction,
)
from tests.test_support.postgres_query_plan import plan_index_names
from tests.test_support.transaction_processing import (
    booked_transaction_event,
    canonical_transaction_record,
    instrument_record,
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


async def test_avco_replay_statement_count_is_bounded_and_lot_read_is_indexed(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    small_sell = await _seed_ordered_avco_key(
        async_db_session,
        portfolio_id="PORT-AVCO-CAPACITY-SMALL",
        security_id="FO_EQ_AVCO_CAPACITY_SMALL",
        source_count=2,
        identity_offset=1000,
    )
    large_sell = await _seed_ordered_avco_key(
        async_db_session,
        portfolio_id="PORT-AVCO-CAPACITY-LARGE",
        security_id="FO_EQ_AVCO_CAPACITY_LARGE",
        source_count=200,
        identity_offset=2000,
    )
    await _seed_ordered_avco_key(
        async_db_session,
        portfolio_id="PORT-AVCO-CAPACITY-NOISE",
        security_id="FO_EQ_AVCO_CAPACITY_NOISE",
        source_count=1000,
        identity_offset=3000,
    )
    await async_db_session.execute(text("ANALYZE position_lot_state"))
    await async_db_session.commit()
    context = transaction_processing_test_context(async_db_session)

    small_statements = await _process_and_capture_statements(
        session=async_db_session,
        context=context,
        sell=small_sell,
        event_id="transactions.persisted-0-9901",
    )
    large_statements = await _process_and_capture_statements(
        session=async_db_session,
        context=context,
        sell=large_sell,
        event_id="transactions.persisted-0-9902",
    )

    small_cost_state_statements = _cost_state_statements(small_statements)
    large_cost_state_statements = _cost_state_statements(large_statements)
    assert len(small_statements) == len(large_statements)
    # Until #481 persists the source-aware checkpoint, AVCO disposal replays canonical
    # history and writes a complete lot snapshot. SQL statement count stays bounded;
    # selected and written row volume intentionally scales with the source count.
    assert len(small_cost_state_statements) == len(large_cost_state_statements) == 3
    assert (
        sum(
            statement.startswith("SELECT position_lot_state.id")
            for statement in large_cost_state_statements
        )
        == 1
    )
    assert (
        sum(
            statement.startswith("UPDATE position_lot_state")
            for statement in large_cost_state_statements
        )
        == 1
    )
    assert (
        sum(
            "sum(position_lot_state.open_quantity)" in statement
            for statement in large_cost_state_statements
        )
        == 0
    )

    plan = await async_db_session.scalar(
        text(
            """
            EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
            SELECT sum(open_quantity), sum(lot_cost_local), sum(lot_cost_base)
            FROM position_lot_state
            WHERE trim(portfolio_id) = :portfolio_id
              AND trim(security_id) = :security_id
            """
        ),
        {
            "portfolio_id": "PORT-AVCO-CAPACITY-SMALL",
            "security_id": "FO_EQ_AVCO_CAPACITY_SMALL",
        },
    )
    assert "ix_position_lot_norm_port_sec" in plan_index_names(plan)


async def test_average_cost_pool_lock_is_scoped_to_portfolio_security_key(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    first_portfolio_id = "PORT-AVCO-LOCK-FIRST"
    first_security_id = "FO_EQ_AVCO_LOCK_FIRST"
    second_portfolio_id = "PORT-AVCO-LOCK-SECOND"
    second_security_id = "FO_EQ_AVCO_LOCK_SECOND"
    await _seed_ordered_avco_key(
        async_db_session,
        portfolio_id=first_portfolio_id,
        security_id=first_security_id,
        source_count=1,
        identity_offset=4000,
    )
    await _seed_ordered_avco_key(
        async_db_session,
        portfolio_id=second_portfolio_id,
        security_id=second_security_id,
        source_count=1,
        identity_offset=5000,
    )
    session_factory = transaction_processing_test_context(async_db_session).session_factory

    async with session_factory() as first_session, session_factory() as second_session:
        first_transaction = first_session.begin()
        second_transaction = second_session.begin()
        await first_transaction.start()
        await second_transaction.start()
        first_repository = SqlAlchemyAverageCostPoolRepository(first_session)
        second_repository = SqlAlchemyAverageCostPoolRepository(second_session)
        try:
            first_record = await first_repository.get_average_cost_pool_checkpoint_record(
                portfolio_id=first_portfolio_id,
                security_id=first_security_id,
            )
            await second_session.execute(text("SET LOCAL lock_timeout = '200ms'"))
            unrelated_record = await second_repository.get_average_cost_pool_checkpoint_record(
                portfolio_id=second_portfolio_id,
                security_id=second_security_id,
            )

            assert first_record is not None
            assert unrelated_record is not None
            with pytest.raises(DBAPIError):
                await second_repository.get_average_cost_pool_checkpoint_record(
                    portfolio_id=first_portfolio_id,
                    security_id=first_security_id,
                )
        finally:
            await second_session.rollback()
            await first_session.rollback()


async def _seed_ordered_avco_key(
    session: AsyncSession,
    *,
    portfolio_id: str,
    security_id: str,
    source_count: int,
    identity_offset: int,
):
    session.add(portfolio_record(portfolio_id, cost_basis_method="AVCO"))
    session.add(
        instrument_record(
            security_id,
            name=f"AVCO Capacity Equity {identity_offset}",
            isin=f"SG{identity_offset:010d}",
            currency="USD",
        )
    )
    start = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    buys = [
        booked_transaction_event(
            transaction_id=f"BUY-AVCO-CAPACITY-{identity_offset}-{sequence:04d}",
            portfolio_id=portfolio_id,
            security_id=security_id,
            transaction_date=start + timedelta(microseconds=sequence),
            transaction_type="BUY",
            quantity="1",
            price="10",
            gross_amount="10",
            gross_cost=Decimal("10"),
            net_cost=Decimal("10"),
            transaction_fx_rate=Decimal("1"),
            net_cost_local=Decimal("10"),
        )
        for sequence in range(source_count)
    ]
    calculation_inputs = []
    for buy in buys:
        transaction_input = build_cost_basis_engine_input(
            booked_transaction.to_booked_transaction(buy)
        )
        transaction_input["portfolio_base_currency"] = "USD"
        calculation_inputs.append(transaction_input)
    calculation = build_cost_basis_timeline_processor(CostBasisMethod.AVCO).process_transactions(
        existing_transactions_raw=[],
        new_transactions_raw=calculation_inputs,
    )
    assert calculation.errored == []
    calculated_by_id = {
        transaction.transaction_id: transaction for transaction in calculation.processed
    }
    canonical_records = []
    for buy in buys:
        calculated = calculated_by_id[buy.transaction_id]
        record = canonical_transaction_record(buy)
        record.gross_cost = calculated.gross_cost
        record.net_cost = calculated.net_cost
        record.realized_gain_loss = calculated.realized_gain_loss
        record.transaction_fx_rate = calculated.transaction_fx_rate
        record.net_cost_local = calculated.net_cost_local
        record.realized_gain_loss_local = calculated.realized_gain_loss_local
        lineage = calculated.calculation_lineage
        assert lineage is not None
        record.calculation_lineage = lineage.lineage_payload()
        canonical_records.append(record)
    session.add_all(canonical_records)
    await session.commit()
    session.add_all(
        PositionLotState(
            lot_id=f"LOT-{buy.transaction_id}",
            source_transaction_id=buy.transaction_id,
            portfolio_id=portfolio_id,
            instrument_id=security_id,
            security_id=security_id,
            acquisition_date=buy.transaction_date.date(),
            original_quantity=buy.quantity,
            open_quantity=buy.quantity,
            lot_cost_local=buy.gross_transaction_amount,
            lot_cost_base=buy.gross_transaction_amount,
        )
        for buy in buys
    )
    latest_buy = buys[-1]
    checkpoint = _processing_checkpoint(latest_buy)
    await SqlAlchemyCostBasisProcessingStateRepository(
        session
    ).upsert_cost_basis_processing_checkpoint(checkpoint)
    session.add(
        AverageCostPoolState(
            portfolio_id=portfolio_id,
            security_id=security_id,
            instrument_id=security_id,
            representative_source_transaction_id=latest_buy.transaction_id,
            pool_quantity=Decimal(source_count),
            pool_cost_local=Decimal(source_count * 10),
            pool_cost_base=Decimal(source_count * 10),
            state_version="avco-pool-v1",
        )
    )
    await session.commit()
    return booked_transaction_event(
        transaction_id=f"SELL-AVCO-CAPACITY-{identity_offset}",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=start + timedelta(days=1),
        transaction_type="SELL",
        quantity="1",
        price="20",
        gross_amount="20",
    )


def _processing_checkpoint(event) -> CostBasisProcessingCheckpoint:
    raw = build_cost_basis_engine_input(booked_transaction.to_booked_transaction(event))
    raw.update(
        portfolio_base_currency="USD",
        net_cost_local=event.gross_transaction_amount,
        net_cost=event.gross_transaction_amount,
    )
    return CostBasisProcessingCheckpoint.from_transaction(
        EngineTransaction(**raw),
        cost_basis_method="AVCO",
    )


async def _process_and_capture_statements(
    *,
    session: AsyncSession,
    context,
    sell,
    event_id: str,
) -> list[str]:
    session.add(canonical_transaction_record(sell))
    await session.commit()
    statements: list[str] = []

    def capture_statement(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
        statements.append(" ".join(statement.split()))

    sync_engine = session.bind.sync_engine
    sqlalchemy_event.listen(sync_engine, "before_cursor_execute", capture_statement)
    try:
        result = await process_booked_transaction(
            context=context,
            event=sell,
            event_id=event_id,
            correlation_id="corr-avco-capacity",
        )
    finally:
        sqlalchemy_event.remove(sync_engine, "before_cursor_execute", capture_statement)
    assert result.status is TransactionProcessingStatus.PROCESSED
    return statements


def _cost_state_statements(statements: list[str]) -> list[str]:
    return [
        statement
        for statement in statements
        if "average_cost_pool_state" in statement or "position_lot_state" in statement
    ]
