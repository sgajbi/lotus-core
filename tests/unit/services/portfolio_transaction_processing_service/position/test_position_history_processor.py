"""Test position-history application orchestration through framework-neutral ports."""

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from src.services.portfolio_transaction_processing_service.app.application.position_history import (
    PositionHistoryProcessor,
)
from src.services.portfolio_transaction_processing_service.app.domain import (
    BookedTransaction,
    PositionHistoryRecord,
    PositionRecalculationState,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    PositionHistoryObserver,
    PositionHistoryRepository,
    PositionRecalculationReason,
    PositionRecalculationStateStore,
    PositionReplayMode,
)


def _transaction(
    transaction_id: str = "TX-001",
    *,
    transaction_date: date = date(2026, 4, 10),
    epoch: int | None = None,
    quantity: Decimal = Decimal("10"),
    net_cost: Decimal = Decimal("100"),
) -> BookedTransaction:
    return BookedTransaction(
        transaction_id=transaction_id,
        portfolio_id="PB-001",
        instrument_id="SEC-001",
        security_id="SEC-001",
        transaction_date=datetime.combine(
            transaction_date, datetime.min.time(), tzinfo=timezone.utc
        ),
        transaction_type="BUY",
        quantity=quantity,
        price=Decimal("10"),
        gross_transaction_amount=quantity * Decimal("10"),
        trade_currency="SGD",
        currency="SGD",
        net_cost=net_cost,
        net_cost_local=net_cost,
        epoch=epoch,
    )


def _state(
    *, epoch: int = 3, watermark_date: date = date(2026, 4, 9), status: str = "CURRENT"
) -> PositionRecalculationState:
    return PositionRecalculationState(
        portfolio_id="PB-001",
        security_id="SEC-001",
        epoch=epoch,
        watermark_date=watermark_date,
        status=status,
    )


def _ports() -> tuple[
    AsyncMock,
    AsyncMock,
    Mock,
    PositionHistoryProcessor,
]:
    repository = AsyncMock(spec=PositionHistoryRepository)
    state_store = AsyncMock(spec=PositionRecalculationStateStore)
    observer = Mock(spec=PositionHistoryObserver)
    state_store.get_or_create.return_value = _state()
    state_store.rearm_generation.return_value = True
    repository.latest_history_date.return_value = None
    repository.latest_completed_snapshot_date.return_value = None
    repository.contains_transaction.return_value = False
    repository.last_record_before.return_value = None
    repository.list_transactions_from.return_value = ()
    repository.list_all_transactions.return_value = ()
    processor = PositionHistoryProcessor(
        repository=repository,
        state_store=state_store,
        observer=observer,
    )
    return repository, state_store, observer, processor


@pytest.mark.asyncio
async def test_processor_discards_stale_epoch_from_single_loaded_position_state() -> None:
    repository, state_store, observer, processor = _ports()
    transaction = _transaction(epoch=2)

    result = await processor.process(transaction)

    assert result.position_record_count == 0
    assert result.rebuilt_transactions == ()
    state_store.get_or_create.assert_awaited_once_with(portfolio_id="PB-001", security_id="SEC-001")
    repository.latest_history_date.assert_not_awaited()
    observer.stale_epoch_discarded.assert_called_once_with(
        transaction=transaction,
        current_epoch=3,
    )


@pytest.mark.asyncio
async def test_processor_materializes_current_history_and_rearms_downstream_generation() -> None:
    repository, state_store, observer, processor = _ports()
    transaction = _transaction()
    repository.list_transactions_from.return_value = (transaction,)

    result = await processor.process(transaction)

    assert result.position_record_count == 1
    assert result.rebuilt_transactions == ()
    repository.acquire_replay_lock.assert_awaited_once_with(
        portfolio_id="PB-001", security_id="SEC-001", epoch=3
    )
    repository.delete_records_from.assert_awaited_once_with(
        portfolio_id="PB-001",
        security_id="SEC-001",
        position_date=date(2026, 4, 10),
        epoch=3,
    )
    records = repository.save_records.await_args.args[0]
    assert records == (
        PositionHistoryRecord(
            portfolio_id="PB-001",
            security_id="SEC-001",
            transaction_id="TX-001",
            position_date=date(2026, 4, 10),
            quantity=Decimal("10"),
            cost_basis=Decimal("100"),
            cost_basis_local=Decimal("100"),
            epoch=3,
        ),
    )
    state_store.rearm_generation.assert_awaited_once_with(
        portfolio_id="PB-001",
        security_id="SEC-001",
        watermark_date=date(2026, 4, 9),
    )
    observer.records_staged.assert_called_once_with(epoch=3, record_count=1)
    observer.generation_rearmed.assert_called_once()


@pytest.mark.asyncio
async def test_processor_acquires_key_lock_before_deleting_current_history() -> None:
    repository, _, _, processor = _ports()
    transaction = _transaction()
    repository.list_transactions_from.return_value = (transaction,)
    call_order: list[str] = []

    async def acquire_lock(**_: object) -> None:
        call_order.append("lock")

    async def delete_records(**_: object) -> int:
        call_order.append("delete")
        return 0

    repository.acquire_replay_lock.side_effect = acquire_lock
    repository.delete_records_from.side_effect = delete_records

    await processor.process(transaction)

    assert call_order[:2] == ["lock", "delete"]


@pytest.mark.asyncio
async def test_processor_does_not_rearm_generation_when_no_history_is_materialized() -> None:
    repository, state_store, observer, processor = _ports()

    result = await processor.process(_transaction())

    assert result.position_record_count == 0
    repository.save_records.assert_not_awaited()
    state_store.rearm_generation.assert_not_awaited()
    observer.records_staged.assert_called_once_with(epoch=3, record_count=0)
    observer.generation_rearmed.assert_not_called()


@pytest.mark.asyncio
async def test_processor_coalesces_materialized_backdated_transaction() -> None:
    repository, state_store, observer, processor = _ports()
    transaction = _transaction(transaction_date=date(2026, 4, 10))
    state_store.get_or_create.return_value = _state(watermark_date=date(2026, 4, 20))
    repository.latest_history_date.return_value = date(2026, 4, 19)
    repository.contains_transaction.return_value = True

    result = await processor.process(transaction)

    assert result.position_record_count == 0
    state_store.advance_epoch.assert_not_awaited()
    repository.acquire_replay_lock.assert_not_awaited()
    observer.recalculation_coalesced.assert_called_once_with(
        transaction=transaction,
        epoch=3,
        reason=PositionRecalculationReason.ALREADY_MATERIALIZED,
    )
    observer.replay_work_items.assert_called_once_with(
        mode=PositionReplayMode.COALESCED,
        count=0,
    )


@pytest.mark.asyncio
async def test_processor_rebuilds_backdated_history_in_advanced_epoch() -> None:
    repository, state_store, observer, processor = _ports()
    incoming = _transaction("TX-BACKDATED", transaction_date=date(2026, 4, 10))
    later = _transaction("TX-LATER", transaction_date=date(2026, 4, 12))
    state_store.get_or_create.return_value = _state(watermark_date=date(2026, 4, 20))
    repository.latest_history_date.return_value = date(2026, 4, 19)
    repository.latest_completed_snapshot_date.return_value = date(2026, 4, 21)
    repository.list_all_transactions.return_value = (later,)
    state_store.advance_epoch.return_value = _state(
        epoch=4,
        watermark_date=date(2026, 4, 9),
        status="REPROCESSING",
    )

    result = await processor.process(incoming)

    expected_rebuilt = (
        replace(incoming, epoch=4),
        replace(later, epoch=4),
    )
    assert result.position_record_count == 2
    assert result.rebuilt_transactions == expected_rebuilt
    state_store.advance_epoch.assert_awaited_once_with(
        portfolio_id="PB-001",
        security_id="SEC-001",
        expected_epoch=3,
        watermark_date=date(2026, 4, 9),
    )
    repository.acquire_replay_lock.assert_awaited_once_with(
        portfolio_id="PB-001", security_id="SEC-001", epoch=4
    )
    repository.delete_records_from.assert_awaited_once_with(
        portfolio_id="PB-001",
        security_id="SEC-001",
        position_date=date(2026, 4, 10),
        epoch=4,
    )
    assert repository.save_records.await_args.args[0][1].transaction_id == "TX-LATER"
    observer.backdated_recalculation_detected.assert_called_once()
    observer.epoch_advanced.assert_called_once()
    observer.replay_work_items.assert_called_once_with(
        mode=PositionReplayMode.INLINE_REBUILD,
        count=2,
    )
    observer.history_rebuilt.assert_called_once_with(
        transaction=incoming,
        epoch=4,
        record_count=2,
        earliest_transaction_date=date(2026, 4, 10),
    )


@pytest.mark.asyncio
async def test_processor_coalesces_backdated_rebuild_when_epoch_compare_and_set_loses() -> None:
    repository, state_store, observer, processor = _ports()
    transaction = _transaction(transaction_date=date(2026, 4, 10))
    state_store.get_or_create.return_value = _state(watermark_date=date(2026, 4, 20))
    repository.latest_history_date.return_value = date(2026, 4, 19)
    state_store.advance_epoch.return_value = None

    result = await processor.process(transaction)

    assert result.position_record_count == 0
    repository.acquire_replay_lock.assert_not_awaited()
    observer.recalculation_coalesced.assert_called_once_with(
        transaction=transaction,
        epoch=3,
        reason=PositionRecalculationReason.STALE_EPOCH,
    )


@pytest.mark.asyncio
async def test_processor_correction_rebuild_bypasses_materialized_coalescing() -> None:
    repository, state_store, _, processor = _ports()
    incoming = _transaction(transaction_date=date(2026, 4, 10))
    state_store.get_or_create.return_value = _state(watermark_date=date(2026, 4, 20))
    repository.latest_history_date.return_value = date(2026, 4, 19)
    repository.contains_transaction.return_value = True
    repository.list_all_transactions.return_value = (incoming,)
    state_store.advance_epoch.return_value = _state(
        epoch=4,
        watermark_date=date(2026, 4, 9),
        status="REPROCESSING",
    )

    result = await processor.process(incoming, rebuild_existing=True)

    assert result.position_record_count == 1
    state_store.advance_epoch.assert_awaited_once()
    repository.acquire_replay_lock.assert_awaited_once()
