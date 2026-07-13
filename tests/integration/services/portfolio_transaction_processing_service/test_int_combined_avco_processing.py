from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    AverageCostPoolState,
    Cashflow,
    CostBasisProcessingState,
    OutboxEvent,
    PositionHistory,
    PositionLotState,
    ProcessedEvent,
)
from portfolio_common.database_models import Transaction as DBTransaction
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    SELL_AVCO_POLICY_ID,
)
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.application import (
    TransactionProcessingStatus,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    CostCalculatorRepository,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.sqlalchemy_unit_of_work import (  # noqa: E501
    TRANSACTION_PROCESSING_SERVICE_NAME,
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


async def test_combined_avco_disposal_reconciles_pooled_and_source_cost_basis(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-COMBINED-AVCO-01"
    security_id = "FO_EQ_COMBINED_AVCO_01"
    first_buy = booked_transaction_event(
        transaction_id="BUY-COMBINED-AVCO-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="100",
        price="10",
        gross_amount="1000",
    )
    second_buy = booked_transaction_event(
        transaction_id="BUY-COMBINED-AVCO-02",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="100",
        price="12",
        gross_amount="1200",
    )
    disposal = booked_transaction_event(
        transaction_id="SELL-COMBINED-AVCO-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 6, 10, 10, 0, tzinfo=timezone.utc),
        transaction_type="SELL",
        quantity="50",
        price="15",
        gross_amount="750",
    )
    async_db_session.add(portfolio_record(portfolio_id, cost_basis_method="AVCO"))
    async_db_session.add(
        instrument_record(
            security_id,
            name="Combined Processing AVCO Equity",
            isin="SG0000000004",
            currency="USD",
        )
    )
    context = transaction_processing_test_context(async_db_session)

    first_buy_result = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=first_buy,
        event_id="transactions.persisted-0-9401",
        correlation_id="corr-combined-avco-buy-01",
    )
    second_buy_result = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=second_buy,
        event_id="transactions.persisted-0-9402",
        correlation_id="corr-combined-avco-buy-02",
    )
    disposal_result = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=disposal,
        event_id="transactions.persisted-0-9403",
        correlation_id="corr-combined-avco-sell-01",
    )
    duplicate_disposal_result = await process_booked_transaction(
        context=context,
        event=disposal,
        event_id="transactions.persisted-0-9403",
        correlation_id="corr-combined-avco-sell-01",
    )

    assert first_buy_result.status is TransactionProcessingStatus.PROCESSED
    assert second_buy_result.status is TransactionProcessingStatus.PROCESSED
    assert disposal_result.status is TransactionProcessingStatus.PROCESSED
    assert duplicate_disposal_result.status is TransactionProcessingStatus.DUPLICATE

    async with context.session_factory() as verification_session:
        persisted_disposal = (
            await verification_session.execute(
                select(DBTransaction).where(DBTransaction.transaction_id == disposal.transaction_id)
            )
        ).scalar_one()
        source_lots = (
            (
                await verification_session.execute(
                    select(PositionLotState)
                    .where(PositionLotState.portfolio_id == portfolio_id)
                    .order_by(PositionLotState.source_transaction_id)
                )
            )
            .scalars()
            .all()
        )
        cashflows = (
            (
                await verification_session.execute(
                    select(Cashflow)
                    .where(Cashflow.portfolio_id == portfolio_id)
                    .order_by(Cashflow.cashflow_date)
                )
            )
            .scalars()
            .all()
        )
        positions = (
            (
                await verification_session.execute(
                    select(PositionHistory)
                    .where(
                        PositionHistory.portfolio_id == portfolio_id,
                        PositionHistory.security_id == security_id,
                    )
                    .order_by(PositionHistory.position_date)
                )
            )
            .scalars()
            .all()
        )
        pool_state = (
            await verification_session.execute(
                select(AverageCostPoolState).where(
                    AverageCostPoolState.portfolio_id == portfolio_id,
                    AverageCostPoolState.security_id == security_id,
                )
            )
        ).scalar_one()

    assert persisted_disposal.calculation_policy_id == SELL_AVCO_POLICY_ID
    assert persisted_disposal.net_cost == Decimal("-550")
    assert persisted_disposal.realized_gain_loss == Decimal("200")
    assert [
        (
            lot.source_transaction_id,
            lot.open_quantity,
            lot.lot_cost_local,
            lot.lot_cost_base,
        )
        for lot in source_lots
    ] == [
        (first_buy.transaction_id, Decimal("75"), Decimal("750"), Decimal("750")),
        (second_buy.transaction_id, Decimal("75"), Decimal("900"), Decimal("900")),
    ]
    assert sum(lot.open_quantity for lot in source_lots) == Decimal("150")
    assert sum(lot.lot_cost_base for lot in source_lots) == Decimal("1650")
    assert pool_state.pool_quantity == Decimal("150")
    assert pool_state.pool_cost_local == Decimal("1650")
    assert pool_state.pool_cost_base == Decimal("1650")
    assert pool_state.representative_source_transaction_id == second_buy.transaction_id
    assert pool_state.state_version == "avco-pool-v1"
    assert [(cashflow.classification, cashflow.amount) for cashflow in cashflows] == [
        ("INVESTMENT_OUTFLOW", Decimal("-1000")),
        ("INVESTMENT_OUTFLOW", Decimal("-1200")),
        ("INVESTMENT_INFLOW", Decimal("750")),
    ]
    assert [
        (position.quantity, position.cost_basis, position.cost_basis_local)
        for position in positions
    ] == [
        (Decimal("100"), Decimal("1000"), Decimal("1000")),
        (Decimal("200"), Decimal("2200"), Decimal("2200")),
        (Decimal("150"), Decimal("1650"), Decimal("1650")),
    ]


async def test_non_lot_avco_rebuild_repairs_source_lots_with_pool_checkpoint(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-COMBINED-AVCO-REBUILD-01"
    security_id = "FO_EQ_COMBINED_AVCO_REBUILD_01"
    events = (
        booked_transaction_event(
            transaction_id="BUY-COMBINED-AVCO-REBUILD-01",
            portfolio_id=portfolio_id,
            security_id=security_id,
            transaction_date=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
            transaction_type="BUY",
            quantity="100",
            price="10",
            gross_amount="1000",
        ),
        booked_transaction_event(
            transaction_id="BUY-COMBINED-AVCO-REBUILD-02",
            portfolio_id=portfolio_id,
            security_id=security_id,
            transaction_date=datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc),
            transaction_type="BUY",
            quantity="100",
            price="12",
            gross_amount="1200",
        ),
        booked_transaction_event(
            transaction_id="SELL-COMBINED-AVCO-REBUILD-01",
            portfolio_id=portfolio_id,
            security_id=security_id,
            transaction_date=datetime(2026, 6, 10, 10, 0, tzinfo=timezone.utc),
            transaction_type="SELL",
            quantity="50",
            price="15",
            gross_amount="750",
        ),
    )
    dividend = booked_transaction_event(
        transaction_id="DIVIDEND-COMBINED-AVCO-REBUILD-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc),
        transaction_type="DIVIDEND",
        quantity="0",
        price="0",
        gross_amount="30",
        cash_entry_mode="AUTO_GENERATE",
    )
    async_db_session.add(portfolio_record(portfolio_id, cost_basis_method="AVCO"))
    async_db_session.add(
        instrument_record(
            security_id,
            name="Combined Processing AVCO Rebuild Equity",
            isin="SG0000000095",
            currency="USD",
        )
    )
    context = transaction_processing_test_context(async_db_session)
    for offset, event in enumerate(events, start=9501):
        await persist_and_process_booked_transaction(
            session=async_db_session,
            context=context,
            event=event,
            event_id=f"transactions.persisted-0-{offset}",
            correlation_id="corr-combined-avco-rebuild",
        )

    async with context.session_factory() as corruption_session:
        source_lots = (
            (
                await corruption_session.execute(
                    select(PositionLotState)
                    .where(PositionLotState.portfolio_id == portfolio_id)
                    .order_by(PositionLotState.source_transaction_id)
                )
            )
            .scalars()
            .all()
        )
        for source_lot, quantity, cost in zip(
            source_lots,
            (Decimal("100"), Decimal("100")),
            (Decimal("1000"), Decimal("1200")),
            strict=True,
        ):
            source_lot.open_quantity = quantity
            source_lot.lot_cost_local = cost
            source_lot.lot_cost_base = cost
        await corruption_session.execute(
            delete(CostBasisProcessingState).where(
                CostBasisProcessingState.portfolio_id == portfolio_id,
                CostBasisProcessingState.security_id == security_id,
            )
        )
        await corruption_session.commit()

    dividend_result = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=dividend,
        event_id="transactions.persisted-0-9504",
        correlation_id="corr-combined-avco-rebuild",
    )

    async with context.session_factory() as verification_session:
        repaired_source_lots = (
            (
                await verification_session.execute(
                    select(PositionLotState)
                    .where(PositionLotState.portfolio_id == portfolio_id)
                    .order_by(PositionLotState.source_transaction_id)
                )
            )
            .scalars()
            .all()
        )
        pool_state = await verification_session.scalar(
            select(AverageCostPoolState).where(
                AverageCostPoolState.portfolio_id == portfolio_id,
                AverageCostPoolState.security_id == security_id,
            )
        )

    assert dividend_result.status is TransactionProcessingStatus.PROCESSED
    assert [
        (lot.source_transaction_id, lot.open_quantity, lot.lot_cost_base)
        for lot in repaired_source_lots
    ] == [
        (events[0].transaction_id, Decimal("75"), Decimal("750")),
        (events[1].transaction_id, Decimal("75"), Decimal("900")),
    ]
    assert pool_state is not None
    assert pool_state.pool_quantity == Decimal("150")
    assert pool_state.pool_cost_base == Decimal("1650")


async def test_avco_checkpoint_failure_rolls_back_all_combined_processing_outputs(
    clean_db,
    async_db_session: AsyncSession,
    monkeypatch,
) -> None:
    portfolio_id = "PORT-COMBINED-AVCO-ROLLBACK-01"
    security_id = "FO_EQ_COMBINED_AVCO_ROLLBACK_01"
    first_buy = booked_transaction_event(
        transaction_id="BUY-COMBINED-AVCO-ROLLBACK-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="100",
        price="10",
        gross_amount="1000",
    )
    second_buy = booked_transaction_event(
        transaction_id="BUY-COMBINED-AVCO-ROLLBACK-02",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="100",
        price="12",
        gross_amount="1200",
    )
    disposal = booked_transaction_event(
        transaction_id="SELL-COMBINED-AVCO-ROLLBACK-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 6, 10, 10, 0, tzinfo=timezone.utc),
        transaction_type="SELL",
        quantity="50",
        price="15",
        gross_amount="750",
    )
    event_id = "transactions.persisted-0-9493"
    async_db_session.add(portfolio_record(portfolio_id, cost_basis_method="AVCO"))
    async_db_session.add(
        instrument_record(
            security_id,
            name="Combined Processing AVCO Rollback Equity",
            isin="SG0000000094",
            currency="USD",
        )
    )
    context = transaction_processing_test_context(async_db_session)
    for offset, event in enumerate((first_buy, second_buy), start=9491):
        await persist_and_process_booked_transaction(
            session=async_db_session,
            context=context,
            event=event,
            event_id=f"transactions.persisted-0-{offset}",
            correlation_id="corr-combined-avco-rollback",
        )

    original_upsert = CostCalculatorRepository.upsert_average_cost_pool_checkpoint

    async def fail_disposal_checkpoint(
        repository: CostCalculatorRepository,
        checkpoint,
    ) -> None:
        if checkpoint.quantity == Decimal("150"):
            raise RuntimeError("average cost pool checkpoint persistence failed")
        await original_upsert(repository, checkpoint)

    monkeypatch.setattr(
        CostCalculatorRepository,
        "upsert_average_cost_pool_checkpoint",
        fail_disposal_checkpoint,
    )

    with pytest.raises(RuntimeError, match="checkpoint persistence failed"):
        await persist_and_process_booked_transaction(
            session=async_db_session,
            context=context,
            event=disposal,
            event_id=event_id,
            correlation_id="corr-combined-avco-rollback",
        )

    async with context.session_factory() as verification_session:
        persisted_disposal = await verification_session.scalar(
            select(DBTransaction).where(DBTransaction.transaction_id == disposal.transaction_id)
        )
        source_lots = (
            (
                await verification_session.execute(
                    select(PositionLotState)
                    .where(PositionLotState.portfolio_id == portfolio_id)
                    .order_by(PositionLotState.source_transaction_id)
                )
            )
            .scalars()
            .all()
        )
        pool_state = await verification_session.scalar(
            select(AverageCostPoolState).where(
                AverageCostPoolState.portfolio_id == portfolio_id,
                AverageCostPoolState.security_id == security_id,
            )
        )
        cashflow = await verification_session.scalar(
            select(Cashflow).where(Cashflow.transaction_id == disposal.transaction_id)
        )
        position = await verification_session.scalar(
            select(PositionHistory).where(PositionHistory.transaction_id == disposal.transaction_id)
        )
        processed_event = await verification_session.scalar(
            select(ProcessedEvent).where(
                ProcessedEvent.event_id == event_id,
                ProcessedEvent.service_name == TRANSACTION_PROCESSING_SERVICE_NAME,
            )
        )
        outbox_event = await verification_session.scalar(
            select(OutboxEvent).where(OutboxEvent.aggregate_id == disposal.transaction_id)
        )

    assert persisted_disposal is not None
    assert persisted_disposal.net_cost is None
    assert persisted_disposal.realized_gain_loss is None
    assert [
        (lot.source_transaction_id, lot.open_quantity, lot.lot_cost_base) for lot in source_lots
    ] == [
        (first_buy.transaction_id, Decimal("100"), Decimal("1000")),
        (second_buy.transaction_id, Decimal("100"), Decimal("1200")),
    ]
    assert pool_state is not None
    assert pool_state.pool_quantity == Decimal("200")
    assert pool_state.pool_cost_local == Decimal("2200")
    assert pool_state.pool_cost_base == Decimal("2200")
    assert cashflow is None
    assert position is None
    assert processed_event is None
    assert outbox_event is None
