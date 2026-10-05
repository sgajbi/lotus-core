from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    Cashflow,
    OutboxEvent,
    PipelineStageState,
    PositionHistory,
    PositionState,
    ProcessedEvent,
    TransactionCost,
)
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.domain.calculation_lineage import build_calculation_lineage
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.persistence_service.app.repositories.transaction_db_repo import (
    TransactionDBRepository,
)
from src.services.portfolio_transaction_processing_service.app.application import (
    TransactionProcessingRejected,
    TransactionProcessingStatus,
)
from src.services.portfolio_transaction_processing_service.app.application.cashflow_processing.use_case import (  # noqa: E501
    ProcessTransactionCashflowUseCase,
)
from src.services.portfolio_transaction_processing_service.app.application.position_history import (
    PositionHistoryProcessor,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    build_cost_basis_engine_input,
    has_governed_transaction_cost_authority,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    SqlAlchemyCostBasisProcessingStateRepository,
    SqlAlchemyCostBasisTransactionRepository,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis.processing_adapter import (  # noqa: E501
    CostBasisProcessingAdapter,
)
from tests.test_support.async_task_coordination import (
    cancel_pending_tasks,
    wait_for_postgres_advisory_lock_wait,
    wait_for_task_signal,
)
from tests.test_support.transaction_processing import (
    TransactionProcessingTestContext,
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
    pytest.mark.resilience,
]


@pytest.mark.parametrize("first_cost_lock_transaction", ["middle", "earliest"])
@pytest.mark.parametrize("fee_presence", ["positive", "zero", "absent"])
async def test_concurrent_backdated_triggers_coalesce_after_one_current_epoch_rebuild(
    clean_db,
    async_db_session: AsyncSession,
    first_cost_lock_transaction: str,
    fee_presence: str,
    monkeypatch: pytest.MonkeyPatch,
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
        trade_fee="99",
        brokerage=Decimal("1.25")
        if fee_presence == "positive"
        else (Decimal("0") if fee_presence == "zero" else None),
        stamp_duty=Decimal("0.75")
        if fee_presence == "positive"
        else (Decimal("0") if fee_presence == "zero" else None),
        exchange_fee=Decimal("0") if fee_presence == "zero" else None,
        gst=Decimal("0") if fee_presence == "zero" else None,
        other_fees=Decimal("0") if fee_presence == "zero" else None,
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
    expected_cost = (
        Decimal("50")
        + {"positive": Decimal("2"), "zero": Decimal("0"), "absent": Decimal("99")}[fee_presence]
    )
    await persist_and_process_booked_transaction(
        session=async_db_session,
        context=context,
        event=current_buy,
        event_id="transactions.persisted-0-4860",
        correlation_id="corr-backdated-coalesce-current",
    )

    raw_transactions = TransactionDBRepository(async_db_session)
    await raw_transactions.create_or_update_transaction(earliest_buy)
    await raw_transactions.create_or_update_transaction(middle_buy)
    await async_db_session.flush()
    stale_lineage = build_calculation_lineage(
        algorithm_id="foreign-transaction-cost-calculation",
        algorithm_version=1,
        intermediate_precision=28,
        input_payload={"transaction_id": earliest_buy.transaction_id},
        output_payload={"net_cost": Decimal("999")},
    ).lineage_payload()
    await async_db_session.execute(
        update(DBTransaction)
        .where(DBTransaction.transaction_id == earliest_buy.transaction_id)
        .values(
            trade_fee=Decimal("99"),
            net_cost=Decimal("999"),
            net_cost_local=Decimal("999"),
            calculation_lineage=stale_lineage,
        )
    )
    await async_db_session.commit()
    original_source_hash = await async_db_session.scalar(
        select(DBTransaction.payload_fingerprint).where(
            DBTransaction.transaction_id == earliest_buy.transaction_id
        )
    )
    assert original_source_hash is not None
    await async_db_session.commit()

    first_lock_acquired = asyncio.Event()
    release_first_lock = asyncio.Event()
    second_lock_attempted = asyncio.Event()
    second_lock_acquired = asyncio.Event()
    release_second_lock = asyncio.Event()
    second_backend_pid: list[int] = []
    first_task: asyncio.Task | None = None
    original_acquire_lock = (
        SqlAlchemyCostBasisProcessingStateRepository.acquire_cost_basis_processing_lock
    )

    async def acquire_cost_basis_processing_lock(
        repository: SqlAlchemyCostBasisProcessingStateRepository,
        portfolio_id: str,
        security_id: str,
    ) -> None:
        if asyncio.current_task() is first_task:
            await original_acquire_lock(repository, portfolio_id, security_id)
            first_lock_acquired.set()
            await release_first_lock.wait()
            return

        backend_pid = await repository._session.scalar(text("SELECT pg_backend_pid()"))
        assert backend_pid is not None
        second_backend_pid.append(backend_pid)
        second_lock_attempted.set()
        await original_acquire_lock(repository, portfolio_id, security_id)
        second_lock_acquired.set()
        await release_second_lock.wait()

    monkeypatch.setattr(
        SqlAlchemyCostBasisProcessingStateRepository,
        "acquire_cost_basis_processing_lock",
        acquire_cost_basis_processing_lock,
    )
    event_by_order = {
        "earliest": (
            earliest_buy,
            "transactions.persisted-0-4861",
            "corr-backdated-coalesce-earliest",
        ),
        "middle": (
            middle_buy,
            "transactions.persisted-0-4862",
            "corr-backdated-coalesce-middle",
        ),
    }
    second_cost_lock_transaction = (
        "earliest" if first_cost_lock_transaction == "middle" else "middle"
    )
    first_event, first_event_id, first_correlation_id = event_by_order[first_cost_lock_transaction]
    second_event, second_event_id, second_correlation_id = event_by_order[
        second_cost_lock_transaction
    ]
    first_task = asyncio.create_task(
        process_booked_transaction(
            context=context,
            event=first_event,
            event_id=first_event_id,
            correlation_id=first_correlation_id,
        )
    )
    second_task: asyncio.Task | None = None
    try:
        await wait_for_task_signal(first_task, first_lock_acquired, timeout=5)
        second_task = asyncio.create_task(
            process_booked_transaction(
                context=context,
                event=second_event,
                event_id=second_event_id,
                correlation_id=second_correlation_id,
            )
        )
        await wait_for_task_signal(second_task, second_lock_attempted, timeout=5)
        assert len(second_backend_pid) == 1
        await wait_for_postgres_advisory_lock_wait(
            second_task,
            context.session_factory,
            backend_pid=second_backend_pid[0],
            timeout=5,
        )
        assert second_lock_acquired.is_set() is False
        release_first_lock.set()
        await wait_for_task_signal(second_task, second_lock_acquired, timeout=15)
        await first_task
        async with context.session_factory() as first_committed:
            first_flows = list(
                (
                    await first_committed.scalars(
                        select(Cashflow).where(
                            Cashflow.portfolio_id == portfolio_id, Cashflow.epoch == 1
                        )
                    )
                ).all()
            )
            first_source_hash = await first_committed.scalar(
                select(DBTransaction.payload_fingerprint).where(
                    DBTransaction.transaction_id == earliest_buy.transaction_id
                )
            )
        assert {row.transaction_id: row.amount for row in first_flows} == {
            earliest_buy.transaction_id: -expected_cost,
            middle_buy.transaction_id: Decimal("-30"),
            current_buy.transaction_id: Decimal("-100"),
        }
        assert all(row.economic_event_id and row.linked_transaction_group_id for row in first_flows)
        assert all(row.calculation_lineage for row in first_flows)
        assert first_source_hash == original_source_hash
        release_second_lock.set()
        results = await asyncio.wait_for(
            asyncio.gather(first_task, second_task),
            timeout=15,
        )
        assert second_lock_acquired.is_set() is True
    finally:
        release_first_lock.set()
        release_second_lock.set()
        await cancel_pending_tasks(first_task, second_task)

    assert sorted(result.position_record_count for result in results) == [0, 3]
    assert all(result.replay_queued_count == 0 for result in results)
    assert sorted(result.processed_transaction_ids for result in results) == sorted(
        [(earliest_buy.transaction_id,), (middle_buy.transaction_id,)]
    )

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
        processed_event_count = await verification_session.scalar(
            select(func.count(OutboxEvent.id)).where(
                OutboxEvent.aggregate_id == portfolio_id,
                OutboxEvent.event_type == "ProcessedTransactionPersisted",
            )
        )
        canonical_transactions = list(
            (
                await verification_session.scalars(
                    select(DBTransaction)
                    .where(
                        DBTransaction.portfolio_id == portfolio_id,
                        DBTransaction.security_id == security_id,
                    )
                    .order_by(DBTransaction.transaction_date, DBTransaction.transaction_id)
                )
            ).all()
        )
        transaction_costs = list(
            (
                await verification_session.scalars(
                    select(TransactionCost)
                    .where(TransactionCost.transaction_id == earliest_buy.transaction_id)
                    .order_by(TransactionCost.fee_type)
                )
            ).all()
        )
        governed_history = await SqlAlchemyCostBasisTransactionRepository(
            verification_session
        ).get_transaction_history(portfolio_id, security_id)

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
        expected_cost,
        expected_cost + Decimal("30"),
        expected_cost + Decimal("130"),
    ]
    assert [transaction.net_cost for transaction in canonical_transactions] == [
        expected_cost,
        Decimal("30"),
        Decimal("100"),
    ]
    assert [transaction.net_cost_local for transaction in canonical_transactions] == [
        expected_cost,
        Decimal("30"),
        Decimal("100"),
    ]
    expected_fees = {
        "positive": [("brokerage", Decimal("1.25"), "USD"), ("stamp_duty", Decimal("0.75"), "USD")],
        "zero": [],
        "absent": [("brokerage", Decimal("99"), "USD")],
    }
    assert [(row.fee_type, row.amount, row.currency) for row in transaction_costs] == (
        expected_fees[fee_presence]
    )
    assert all(
        transaction.calculation_lineage is not None for transaction in canonical_transactions
    )
    governed_authority_by_transaction = {
        transaction.transaction_id: has_governed_transaction_cost_authority(
            {
                **build_cost_basis_engine_input(transaction),
                "portfolio_base_currency": "USD",
                "product_type": "EQUITY",
                "asset_class": "Equity",
            }
        )
        for transaction in governed_history
    }
    assert all(governed_authority_by_transaction.values()), governed_authority_by_transaction
    assert all(position.calculation_lineage is not None for position in current_positions)
    assert processed_event_count == 3
    assert replay_event_count == 0


async def _first_delivery_financial_evidence(
    context: TransactionProcessingTestContext, portfolio_id: str
) -> dict[str, object]:
    """Read independent committed facts after the producing UOW has left its locks."""
    selections = {
        "sources": select(
            DBTransaction.transaction_id,
            DBTransaction.payload_fingerprint,
            DBTransaction.net_cost,
            DBTransaction.net_cost_local,
            DBTransaction.calculation_lineage,
        )
        .where(DBTransaction.portfolio_id == portfolio_id)
        .order_by(DBTransaction.transaction_id),
        "positions": select(
            PositionHistory.transaction_id,
            PositionHistory.position_date,
            PositionHistory.epoch,
            PositionHistory.quantity,
        )
        .where(PositionHistory.portfolio_id == portfolio_id)
        .order_by(
            PositionHistory.position_date, PositionHistory.transaction_id, PositionHistory.epoch
        ),
        "cashflows": select(
            Cashflow.transaction_id,
            Cashflow.epoch,
            Cashflow.amount,
            Cashflow.classification,
            Cashflow.timing,
            Cashflow.is_position_flow,
            Cashflow.is_portfolio_flow,
            Cashflow.calculation_lineage,
        )
        .where(Cashflow.portfolio_id == portfolio_id)
        .order_by(Cashflow.transaction_id, Cashflow.epoch),
        "semantic_receipts": select(
            ProcessedEvent.tenant_id,
            ProcessedEvent.service_name,
            ProcessedEvent.event_id,
            ProcessedEvent.semantic_key,
            ProcessedEvent.payload_fingerprint,
        )
        .where(ProcessedEvent.portfolio_id == portfolio_id)
        .order_by(ProcessedEvent.tenant_id, ProcessedEvent.service_name, ProcessedEvent.event_id),
        "readiness": select(
            PipelineStageState.transaction_id,
            PipelineStageState.epoch,
            PipelineStageState.status,
            PipelineStageState.cost_event_seen,
            PipelineStageState.cashflow_event_seen,
        )
        .where(PipelineStageState.portfolio_id == portfolio_id)
        .order_by(PipelineStageState.transaction_id, PipelineStageState.epoch),
        "outbox": select(OutboxEvent.event_type, OutboxEvent.aggregate_id, OutboxEvent.payload)
        .where(OutboxEvent.aggregate_id.like(f"{portfolio_id}%"))
        .order_by(OutboxEvent.id),
    }
    async with context.session_factory() as session:
        evidence = {
            name: [dict(row) for row in (await session.execute(statement)).mappings()]
            for name, statement in selections.items()
        }
        evidence["epoch"] = await session.scalar(
            select(PositionState.epoch).where(PositionState.portfolio_id == portfolio_id)
        )
    return evidence


@pytest.mark.lifecycle
@pytest.mark.parametrize(
    (
        "pending_type",
        "pending_amount",
        "expected_quantity",
        "expected_flow",
        "expected_classification",
        "expected_timing",
        "expected_portfolio_flow",
    ),
    [
        ("DEPOSIT", "500", Decimal("1500"), Decimal("500"), "CASHFLOW_IN", "BOD", True),
        ("SELL", "100", Decimal("900"), Decimal("100"), "INVESTMENT_INFLOW", "EOD", False),
    ],
)
async def test_first_financial_delivery_completes_position_materialized_by_same_day_suffix(
    clean_db,
    async_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    pending_type: str,
    pending_amount: str,
    expected_quantity: Decimal,
    expected_flow: Decimal,
    expected_classification: str,
    expected_timing: str,
    expected_portfolio_flow: bool,
) -> None:
    """Hold later delivery by order, without inventing financial or valuation readiness."""
    portfolio_id = f"PORT-FIRST-FINANCIAL-{pending_type}"
    security_id = f"CASH-FIRST-FINANCIAL-{pending_type}"
    async_db_session.add_all(
        [
            portfolio_record(portfolio_id),
            instrument_record(
                security_id,
                name="First financial delivery cash",
                isin=f"USD-FIRST-{pending_type}",
                currency="USD",
                product_type="Cash",
                asset_class="Cash",
            ),
        ]
    )
    await async_db_session.commit()
    events = tuple(
        booked_transaction_event(
            transaction_id=f"{portfolio_id}-{index}",
            portfolio_id=portfolio_id,
            security_id=security_id,
            transaction_date=when,
            transaction_type=kind,
            quantity=amount,
            price="1",
            gross_amount=amount,
        )
        for index, (when, kind, amount) in enumerate(
            [
                (datetime(2026, 7, 1, 9, tzinfo=timezone.utc), "DEPOSIT", "1000"),
                (datetime(2026, 7, 1, 10, tzinfo=timezone.utc), pending_type, pending_amount),
                (datetime(2026, 7, 2, 9, tzinfo=timezone.utc), "WITHDRAWAL", "100"),
            ]
        )
    )
    repository = TransactionDBRepository(async_db_session)
    for event in events:
        await repository.create_or_update_transaction(event)
    await async_db_session.commit()
    context = transaction_processing_test_context(async_db_session)
    observed_cost: list[dict[str, object]] = []
    observed_position: list[dict[str, object]] = []
    observed_cashflow: list[dict[str, object]] = []
    cost_process = CostBasisProcessingAdapter.process
    position_process = PositionHistoryProcessor.process
    cashflow_process = ProcessTransactionCashflowUseCase.process

    async def observe_cost(adapter, transaction, **kwargs):
        result = await cost_process(adapter, transaction, **kwargs)
        observed_cost.append({"input_id": transaction.transaction_id, "result": asdict(result)})
        return result

    async def observe_position(processor, transaction, **kwargs):
        result = await position_process(processor, transaction, **kwargs)
        observed_position.append({"input_id": transaction.transaction_id, "result": asdict(result)})
        return result

    async def observe_cashflow(processor, transaction, **kwargs):
        result = await cashflow_process(processor, transaction, **kwargs)
        observed_cashflow.append(
            {
                "input_id": transaction.transaction_id,
                "epoch": transaction.epoch,
                "calculation_context": kwargs.get("calculation_context"),
                "result": asdict(result),
            }
        )
        return result

    monkeypatch.setattr(CostBasisProcessingAdapter, "process", observe_cost)
    monkeypatch.setattr(PositionHistoryProcessor, "process", observe_position)
    monkeypatch.setattr(ProcessTransactionCashflowUseCase, "process", observe_cashflow)
    first = await process_booked_transaction(
        context=context, event=events[0], event_id="first-delivery-0", correlation_id=portfolio_id
    )
    before = await _first_delivery_financial_evidence(context, portfolio_id)
    assert first.position_record_count == 3, before
    pending_position = next(
        row for row in before["positions"] if row["transaction_id"] == events[1].transaction_id
    )
    assert pending_position["quantity"] == expected_quantity, before
    assert pending_position["epoch"] == before["epoch"] == 0, before
    assert all(row["payload_fingerprint"] for row in before["sources"]), before
    assert [row["transaction_id"] for row in before["cashflows"]] == [events[0].transaction_id], (
        before
    )
    assert [row["transaction_id"] for row in before["readiness"]] == [events[0].transaction_id], (
        before
    )

    rejection = None
    try:
        await process_booked_transaction(
            context=context,
            event=events[1],
            event_id="first-delivery-1",
            correlation_id=portfolio_id,
        )
    except TransactionProcessingRejected as exc:
        rejection = {
            "reason_code": exc.reason_code,
            "retryable": exc.retryable,
            "detail": exc.detail,
        }
    after = await _first_delivery_financial_evidence(context, portfolio_id)
    diagnostic = {
        "before": before,
        "after": after,
        "cost_results": observed_cost,
        "position_results": observed_position,
        "cashflow_results": observed_cashflow,
        "rejection": rejection,
        "current_booking_expected_flow": expected_flow,
    }
    print(json.dumps(diagnostic, default=str, sort_keys=True))
    assert rejection is None, diagnostic
    pending_flow = next(
        row for row in after["cashflows"] if row["transaction_id"] == events[1].transaction_id
    )
    assert pending_flow["amount"] == expected_flow, diagnostic
    assert pending_flow["classification"] == expected_classification, diagnostic
    assert pending_flow["timing"] == expected_timing, diagnostic
    assert pending_flow["is_position_flow"] is True, diagnostic
    assert pending_flow["is_portfolio_flow"] is expected_portfolio_flow, diagnostic
    assert pending_flow["epoch"] == pending_position["epoch"], diagnostic
    assert pending_flow["calculation_lineage"], diagnostic
    assert pending_flow["calculation_lineage"]["algorithm_id"] == "transaction-cashflow", diagnostic
    assert after["positions"] == before["positions"], diagnostic
    pending_calls = [
        row for row in observed_cashflow if row["input_id"] == events[1].transaction_id
    ]
    assert len(pending_calls) == 1, diagnostic
    assert pending_calls[0]["calculation_context"] == "CURRENT_BOOKING", diagnostic
    assert pending_calls[0]["epoch"] == pending_position["epoch"], diagnostic
    assert (
        sum(row["transaction_id"] == events[1].transaction_id for row in after["cashflows"]) == 1
    ), diagnostic
    assert any(
        row["event_id"] == f"cashflow:{portfolio_id}:{events[1].transaction_id}:0"
        for row in after["semantic_receipts"]
    ), diagnostic
    for event_type in (
        "ProcessedTransactionPersisted",
        "CashflowCalculated",
        "TransactionProcessingCompleted",
    ):
        assert (
            sum(
                row["event_type"] == event_type
                and row["payload"].get("transaction_id") == events[1].transaction_id
                for row in after["outbox"]
            )
            == 1
        ), diagnostic
    pending_ready = next(
        row for row in after["readiness"] if row["transaction_id"] == events[1].transaction_id
    )
    assert pending_ready["status"] == "COMPLETED", diagnostic
    assert pending_ready["cost_event_seen"] and pending_ready["cashflow_event_seen"], diagnostic
    assert any(
        row["event_type"] == "TransactionProcessingCompleted"
        and row["payload"]["transaction_id"] == events[1].transaction_id
        for row in after["outbox"]
    ), diagnostic
    duplicate = await process_booked_transaction(
        context=context,
        event=events[1],
        event_id="first-delivery-1-duplicate",
        correlation_id=portfolio_id,
    )
    assert duplicate.status is TransactionProcessingStatus.DUPLICATE
    repeated = await _first_delivery_financial_evidence(context, portfolio_id)
    assert repeated == after, repeated
