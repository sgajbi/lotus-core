from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.database_models import OutboxEvent, PositionHistory, PositionState
from portfolio_common.database_models import Transaction as DBTransaction
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    SqlAlchemyCostBasisProcessingStateRepository,
)
from tests.test_support.async_task_coordination import (
    cancel_pending_tasks,
    wait_for_postgres_advisory_lock_wait,
    wait_for_task_signal,
)
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


@pytest.mark.parametrize("first_cost_lock_transaction", ["middle", "earliest"])
async def test_concurrent_backdated_triggers_coalesce_after_one_current_epoch_rebuild(
    clean_db,
    async_db_session: AsyncSession,
    first_cost_lock_transaction: str,
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

    first_lock_acquired = asyncio.Event()
    release_first_lock = asyncio.Event()
    second_lock_attempted = asyncio.Event()
    second_lock_acquired = asyncio.Event()
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
        results = await asyncio.wait_for(
            asyncio.gather(first_task, second_task),
            timeout=15,
        )
        assert second_lock_acquired.is_set() is True
    finally:
        release_first_lock.set()
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
    assert [transaction.net_cost for transaction in canonical_transactions] == [
        Decimal("50"),
        Decimal("30"),
        Decimal("100"),
    ]
    assert [transaction.net_cost_local for transaction in canonical_transactions] == [
        Decimal("50"),
        Decimal("30"),
        Decimal("100"),
    ]
    assert all(
        transaction.calculation_lineage is not None for transaction in canonical_transactions
    )
    assert all(position.calculation_lineage is not None for position in current_positions)
    assert processed_event_count == 3
    assert replay_event_count == 0
