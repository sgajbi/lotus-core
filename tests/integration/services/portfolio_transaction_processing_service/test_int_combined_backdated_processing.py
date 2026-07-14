from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    Cashflow,
    CostBasisProcessingState,
    OutboxEvent,
    PipelineStageState,
    PositionHistory,
    PositionLotState,
    PositionState,
    ProcessedEvent,
)
from portfolio_common.database_models import Transaction as DBTransaction
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.application import (
    TransactionProcessingIntent,
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
    assert earlier_result.cashflow_record_count == 2

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
        current_cashflows = (
            (
                await verification_session.execute(
                    select(Cashflow)
                    .where(
                        Cashflow.portfolio_id == portfolio_id,
                        Cashflow.security_id == security_id,
                        Cashflow.epoch == state.epoch,
                    )
                    .order_by(Cashflow.cashflow_date, Cashflow.transaction_id)
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
        current_pipeline_stages = (
            (
                await verification_session.execute(
                    select(PipelineStageState)
                    .where(
                        PipelineStageState.stage_name == "TRANSACTION_PROCESSING",
                        PipelineStageState.portfolio_id == portfolio_id,
                        PipelineStageState.security_id == security_id,
                        PipelineStageState.epoch == state.epoch,
                    )
                    .order_by(PipelineStageState.business_date, PipelineStageState.transaction_id)
                )
            )
            .scalars()
            .all()
        )
        cashflow_signals = (
            (
                await verification_session.execute(
                    select(OutboxEvent).where(
                        OutboxEvent.aggregate_id == portfolio_id,
                        OutboxEvent.event_type == "CashflowCalculated",
                    )
                )
            )
            .scalars()
            .all()
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
    assert [cashflow.transaction_id for cashflow in current_cashflows] == [
        "BUY-COMBINED-EARLIER-01",
        "BUY-COMBINED-LATER-01",
    ]
    assert {cashflow.epoch for cashflow in current_cashflows} == {state.epoch}
    assert [stage.transaction_id for stage in current_pipeline_stages] == [
        "BUY-COMBINED-EARLIER-01",
        "BUY-COMBINED-LATER-01",
    ]
    assert {stage.epoch for stage in current_pipeline_stages} == {state.epoch}
    assert all(stage.cost_event_seen is True for stage in current_pipeline_stages)
    current_cashflow_signal_ids = {
        event.payload["transaction_id"]
        for event in cashflow_signals
        if event.payload.get("epoch", 0) == state.epoch
    }
    assert current_cashflow_signal_ids == {
        stage.transaction_id for stage in current_pipeline_stages
    }
    assert legacy_replay_event_count == 0


async def test_explicit_correction_rebuilds_already_materialized_position_history(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    portfolio_id = "PORT-COMBINED-CORRECTION-01"
    security_id = "SEC-COMBINED-CORRECTION-01"
    first_buy = booked_transaction_event(
        transaction_id="BUY-COMBINED-CORRECTION-DAY1",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="100",
        price="100",
        gross_amount="10000",
    )
    later_buy = booked_transaction_event(
        transaction_id="BUY-COMBINED-CORRECTION-DAY3",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 1, 7, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="50",
        price="120",
        gross_amount="6000",
    )
    async_db_session.add_all(
        [
            portfolio_record(portfolio_id),
            instrument_record(
                security_id,
                name="Combined Correction Equity",
                isin="SG0000000299",
                currency="USD",
            ),
        ]
    )
    await async_db_session.commit()
    context = transaction_processing_test_context(async_db_session)
    await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=first_buy,
        event_id="transactions.persisted-0-9291",
        correlation_id="corr-combined-correction-01",
    )
    await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=later_buy,
        event_id="transactions.persisted-0-9292",
        correlation_id="corr-combined-correction-01",
    )

    await async_db_session.execute(
        update(DBTransaction)
        .where(DBTransaction.transaction_id == first_buy.transaction_id)
        .values(quantity=Decimal("120"), gross_transaction_amount=Decimal("12000"))
    )
    await async_db_session.commit()
    corrected_first_buy = first_buy.model_copy(
        update={
            "quantity": Decimal("120"),
            "gross_transaction_amount": Decimal("12000"),
        }
    )

    correction_result = await process_booked_transaction(
        context=context,
        event=corrected_first_buy,
        event_id="transactions.persisted-0-9293",
        correlation_id="corr-combined-correction-01",
        processing_intent=TransactionProcessingIntent.REPAIR,
    )

    assert correction_result.status is TransactionProcessingStatus.PROCESSED
    assert correction_result.position_record_count == 2
    async with context.session_factory() as verification_session:
        state = (
            await verification_session.execute(
                select(PositionState).where(
                    PositionState.portfolio_id == portfolio_id,
                    PositionState.security_id == security_id,
                )
            )
        ).scalar_one()
        positions = (
            (
                await verification_session.execute(
                    select(PositionHistory)
                    .where(
                        PositionHistory.portfolio_id == portfolio_id,
                        PositionHistory.security_id == security_id,
                        PositionHistory.epoch == state.epoch,
                    )
                    .order_by(PositionHistory.position_date)
                )
            )
            .scalars()
            .all()
        )
        correction_fence_count = int(
            await verification_session.scalar(
                select(func.count())
                .select_from(ProcessedEvent)
                .where(
                    ProcessedEvent.service_name == "portfolio-transaction-processing",
                    ProcessedEvent.semantic_key.like("transaction-correction:v1:%"),
                )
            )
            or 0
        )

    assert state.epoch == 1
    assert [position.quantity for position in positions] == [Decimal("120"), Decimal("170")]
    assert [position.cost_basis for position in positions] == [
        Decimal("12000"),
        Decimal("18000"),
    ]
    assert correction_fence_count == 1


@pytest.mark.parametrize(
    ("cost_basis_method", "expected_corrected_gain"),
    [("FIFO", Decimal("400")), ("AVCO", Decimal("300"))],
)
async def test_backdated_buy_corrects_later_disposal_without_duplicate_delivery(
    clean_db,
    async_db_session: AsyncSession,
    cost_basis_method: str,
    expected_corrected_gain: Decimal,
) -> None:
    method_suffix = cost_basis_method.lower()
    portfolio_id = f"PORT-COMBINED-BACKDATED-COST-{method_suffix}"
    security_id = f"SEC-COMBINED-BACKDATED-COST-{method_suffix}"
    later_buy = booked_transaction_event(
        transaction_id=f"BUY-COMBINED-COST-LATER-{method_suffix}",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="100",
        price="10",
        gross_amount="1000",
    )
    later_sell = booked_transaction_event(
        transaction_id=f"SELL-COMBINED-COST-LATER-{method_suffix}",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 1, 10, 10, 0, tzinfo=timezone.utc),
        transaction_type="SELL",
        quantity="100",
        price="12",
        gross_amount="1200",
    )
    earlier_buy = booked_transaction_event(
        transaction_id=f"BUY-COMBINED-COST-EARLIER-{method_suffix}",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="100",
        price="8",
        gross_amount="800",
    )
    async_db_session.add_all(
        [
            portfolio_record(portfolio_id, cost_basis_method=cost_basis_method),
            instrument_record(
                security_id,
                name="Combined Backdated Cost Equity",
                isin="SG0000000202",
                currency="USD",
            ),
        ]
    )
    await async_db_session.commit()
    context = transaction_processing_test_context(async_db_session)

    for offset, event in enumerate((later_buy, later_sell), start=9301):
        await persist_and_process_booked_transaction(
            session=async_db_session,
            context=context,
            event=event,
            event_id=f"transactions.persisted-0-{offset}",
            correlation_id="corr-combined-backdated-cost-01",
        )

    async with context.session_factory() as verification_session:
        initial_sell_gain = await verification_session.scalar(
            select(DBTransaction.realized_gain_loss).where(
                DBTransaction.transaction_id == later_sell.transaction_id
            )
        )

    result = await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=earlier_buy,
        event_id="transactions.persisted-0-9303",
        correlation_id="corr-combined-backdated-cost-01",
    )

    async with context.session_factory() as verification_session:
        corrected_sell_gain = await verification_session.scalar(
            select(DBTransaction.realized_gain_loss).where(
                DBTransaction.transaction_id == later_sell.transaction_id
            )
        )
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
        cost_checkpoint = (
            await verification_session.execute(
                select(CostBasisProcessingState).where(
                    CostBasisProcessingState.portfolio_id == portfolio_id,
                    CostBasisProcessingState.security_id == security_id,
                )
            )
        ).scalar_one()
        current_pipeline_stages = (
            (
                await verification_session.execute(
                    select(PipelineStageState)
                    .where(
                        PipelineStageState.stage_name == "TRANSACTION_PROCESSING",
                        PipelineStageState.portfolio_id == portfolio_id,
                        PipelineStageState.security_id == security_id,
                        PipelineStageState.epoch == state.epoch,
                    )
                    .order_by(PipelineStageState.business_date, PipelineStageState.transaction_id)
                )
            )
            .scalars()
            .all()
        )
        cashflow_signals = (
            (
                await verification_session.execute(
                    select(OutboxEvent).where(
                        OutboxEvent.aggregate_id == portfolio_id,
                        OutboxEvent.event_type == "CashflowCalculated",
                    )
                )
            )
            .scalars()
            .all()
        )

    assert initial_sell_gain == Decimal("200")
    assert corrected_sell_gain == expected_corrected_gain
    assert result.processed_transaction_ids == (earlier_buy.transaction_id,)
    assert [row.transaction_id for row in current_positions] == [
        earlier_buy.transaction_id,
        later_buy.transaction_id,
        later_sell.transaction_id,
    ]
    assert [row.quantity for row in current_positions] == [
        Decimal("100"),
        Decimal("200"),
        Decimal("100"),
    ]
    assert processed_event_count == 3
    assert cost_checkpoint.latest_transaction_id == later_sell.transaction_id
    assert cost_checkpoint.latest_transaction_date == later_sell.transaction_date
    assert [stage.transaction_id for stage in current_pipeline_stages] == [
        earlier_buy.transaction_id,
        later_buy.transaction_id,
        later_sell.transaction_id,
    ]
    assert {stage.epoch for stage in current_pipeline_stages} == {state.epoch}
    assert all(stage.cost_event_seen is True for stage in current_pipeline_stages)
    current_cashflow_signal_ids = {
        event.payload["transaction_id"]
        for event in cashflow_signals
        if event.payload.get("epoch", 0) == state.epoch
    }
    assert current_cashflow_signal_ids == {
        stage.transaction_id for stage in current_pipeline_stages
    }


async def test_backdated_cost_suffix_failure_rolls_back_all_corrections(
    clean_db,
    async_db_session: AsyncSession,
    monkeypatch,
) -> None:
    portfolio_id = "PORT-COMBINED-BACKDATED-ROLLBACK-01"
    security_id = "SEC-COMBINED-BACKDATED-ROLLBACK-01"
    later_buy = booked_transaction_event(
        transaction_id="BUY-COMBINED-ROLLBACK-LATER-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 2, 5, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="100",
        price="10",
        gross_amount="1000",
    )
    later_sell = booked_transaction_event(
        transaction_id="SELL-COMBINED-ROLLBACK-LATER-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 2, 10, 10, 0, tzinfo=timezone.utc),
        transaction_type="SELL",
        quantity="100",
        price="12",
        gross_amount="1200",
    )
    earlier_buy = booked_transaction_event(
        transaction_id="BUY-COMBINED-ROLLBACK-EARLIER-01",
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_date=datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity="100",
        price="8",
        gross_amount="800",
    )
    async_db_session.add_all(
        [
            portfolio_record(portfolio_id),
            instrument_record(
                security_id,
                name="Combined Backdated Rollback Equity",
                isin="SG0000000203",
                currency="USD",
            ),
        ]
    )
    await async_db_session.commit()
    context = transaction_processing_test_context(async_db_session)
    for offset, event in enumerate((later_buy, later_sell), start=9401):
        await persist_and_process_booked_transaction(
            session=async_db_session,
            context=context,
            event=event,
            event_id=f"transactions.persisted-0-{offset}",
            correlation_id="corr-combined-backdated-rollback-01",
        )

    workflow = context.use_case._unit_of_work_factory.cost_workflow
    persist_processed_transaction = workflow._persist_processed_transaction

    async def fail_later_suffix_persistence(
        *, processed_transaction, repo, lot_states, income_offsets
    ):
        if processed_transaction.transaction_id == later_sell.transaction_id:
            raise RuntimeError("later suffix persistence failed")
        return await persist_processed_transaction(
            processed_transaction=processed_transaction,
            repo=repo,
            lot_states=lot_states,
            income_offsets=income_offsets,
        )

    monkeypatch.setattr(
        workflow,
        "_persist_processed_transaction",
        fail_later_suffix_persistence,
    )

    with pytest.raises(RuntimeError, match="later suffix persistence failed"):
        await persist_and_process_booked_transaction(
            session=async_db_session,
            context=context,
            event=earlier_buy,
            event_id="transactions.persisted-0-9403",
            correlation_id="corr-combined-backdated-rollback-01",
        )

    async with context.session_factory() as verification_session:
        sell_gain = await verification_session.scalar(
            select(DBTransaction.realized_gain_loss).where(
                DBTransaction.transaction_id == later_sell.transaction_id
            )
        )
        earlier_net_cost = await verification_session.scalar(
            select(DBTransaction.net_cost).where(
                DBTransaction.transaction_id == earlier_buy.transaction_id
            )
        )
        state = (
            await verification_session.execute(
                select(PositionState).where(
                    PositionState.portfolio_id == portfolio_id,
                    PositionState.security_id == security_id,
                )
            )
        ).scalar_one()
        earlier_lot_count = int(
            await verification_session.scalar(
                select(func.count())
                .select_from(PositionLotState)
                .where(PositionLotState.source_transaction_id == earlier_buy.transaction_id)
            )
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

    assert sell_gain == Decimal("200")
    assert earlier_net_cost is None
    assert state.epoch == 0
    assert earlier_lot_count == 0
    assert processed_event_count == 2
