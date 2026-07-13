"""Orchestrate deterministic current and backdated position-history materialization."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta

from ..domain.booked_transaction import BookedTransaction
from ..domain.position_history import (
    PositionHistoryRecord,
    PositionRecalculationState,
    build_position_history,
)
from ..domain.position_reducer import plan_backdated_recalculation
from ..ports.position_history import (
    PositionHistoryObserver,
    PositionHistoryRepository,
    PositionRecalculationReason,
    PositionRecalculationStateStore,
    PositionReplayMode,
)


@dataclass(frozen=True, slots=True)
class PositionHistoryProcessingResult:
    """Report records written and transactions rebuilt for dependent stages."""

    position_record_count: int = 0
    rebuilt_transactions: tuple[BookedTransaction, ...] = ()


class PositionHistoryProcessor:
    """Materialize one position key inside the caller-owned unit of work."""

    def __init__(
        self,
        *,
        repository: PositionHistoryRepository,
        state_store: PositionRecalculationStateStore,
        observer: PositionHistoryObserver,
    ) -> None:
        self._repository = repository
        self._state_store = state_store
        self._observer = observer

    async def process(
        self,
        transaction: BookedTransaction,
        *,
        rebuild_existing: bool = False,
    ) -> PositionHistoryProcessingResult:
        """Apply current history or atomically rebuild a backdated position stream."""
        current_state = await self._state_store.get_or_create(
            portfolio_id=transaction.portfolio_id,
            security_id=transaction.security_id,
        )
        message_epoch = transaction.epoch if transaction.epoch is not None else current_state.epoch
        if message_epoch < current_state.epoch:
            self._observer.stale_epoch_discarded(
                transaction=transaction,
                current_epoch=current_state.epoch,
            )
            return PositionHistoryProcessingResult()
        latest_history_date = await self._repository.latest_history_date(
            portfolio_id=transaction.portfolio_id,
            security_id=transaction.security_id,
            epoch=current_state.epoch,
        )
        latest_completed_snapshot_date = await self._repository.latest_completed_snapshot_date(
            portfolio_id=transaction.portfolio_id,
            security_id=transaction.security_id,
            epoch=current_state.epoch,
        )
        transaction_date = transaction.transaction_date.date()
        decision = plan_backdated_recalculation(
            event_epoch=transaction.epoch,
            transaction_date=transaction_date,
            current_watermark_date=current_state.watermark_date,
            latest_position_history_date=latest_history_date,
            latest_completed_snapshot_date=latest_completed_snapshot_date,
        )
        if decision.should_recalculate:
            if decision.recalculation_watermark_date is None:
                raise RuntimeError(
                    "Backdated recalculation decision did not include a rebuild watermark"
                )
            if not rebuild_existing and await self._repository.contains_transaction(
                portfolio_id=transaction.portfolio_id,
                security_id=transaction.security_id,
                transaction_id=transaction.transaction_id,
                epoch=current_state.epoch,
            ):
                self._observer.recalculation_coalesced(
                    transaction=transaction,
                    epoch=current_state.epoch,
                    reason=PositionRecalculationReason.ALREADY_MATERIALIZED,
                )
                self._observer.replay_work_items(mode=PositionReplayMode.COALESCED, count=0)
                return PositionHistoryProcessingResult()
            return await self._rebuild_backdated_history(
                transaction=transaction,
                current_state=current_state,
                effective_completed_date=decision.effective_completed_date,
                replay_watermark_date=decision.recalculation_watermark_date,
                latest_history_date=latest_history_date,
            )

        records = await self._recalculate_current_history(
            transaction=transaction,
            current_state=current_state,
        )
        return PositionHistoryProcessingResult(position_record_count=len(records))

    async def _rebuild_backdated_history(
        self,
        *,
        transaction: BookedTransaction,
        current_state: PositionRecalculationState,
        effective_completed_date: date,
        replay_watermark_date: date,
        latest_history_date: date | None,
    ) -> PositionHistoryProcessingResult:
        self._observer.backdated_recalculation_detected(
            transaction=transaction,
            current_state=current_state,
            effective_completed_date=effective_completed_date,
            latest_history_date=latest_history_date,
        )
        new_state = await self._state_store.advance_epoch(
            portfolio_id=transaction.portfolio_id,
            security_id=transaction.security_id,
            expected_epoch=current_state.epoch,
            watermark_date=replay_watermark_date,
        )
        if new_state is None:
            self._observer.recalculation_coalesced(
                transaction=transaction,
                epoch=current_state.epoch,
                reason=PositionRecalculationReason.STALE_EPOCH,
            )
            return PositionHistoryProcessingResult()
        self._observer.epoch_advanced(transaction=transaction, state=new_state)

        await self._repository.acquire_replay_lock(
            portfolio_id=transaction.portfolio_id,
            security_id=transaction.security_id,
            epoch=new_state.epoch,
        )
        historical_transactions = list(
            await self._repository.list_all_transactions(
                portfolio_id=transaction.portfolio_id,
                security_id=transaction.security_id,
            )
        )
        if not any(
            item.transaction_id == transaction.transaction_id for item in historical_transactions
        ):
            historical_transactions.append(transaction)
        epoch_transactions = tuple(
            replace(item, epoch=new_state.epoch) for item in historical_transactions
        )
        self._observer.replay_work_items(
            mode=PositionReplayMode.INLINE_REBUILD,
            count=len(epoch_transactions),
        )
        earliest_transaction_date = min(item.transaction_date.date() for item in epoch_transactions)
        await self._repository.delete_records_from(
            portfolio_id=transaction.portfolio_id,
            security_id=transaction.security_id,
            position_date=earliest_transaction_date,
            epoch=new_state.epoch,
        )
        records = await self._stage_history(
            anchor=None,
            transactions=epoch_transactions,
            state=new_state,
            transaction_date=earliest_transaction_date,
        )
        transactions_by_id = {item.transaction_id: item for item in epoch_transactions}
        rebuilt_transactions = tuple(
            transactions_by_id[record.transaction_id] for record in records
        )
        self._observer.history_rebuilt(
            transaction=transaction,
            epoch=new_state.epoch,
            record_count=len(records),
            earliest_transaction_date=earliest_transaction_date,
        )
        return PositionHistoryProcessingResult(
            position_record_count=len(records),
            rebuilt_transactions=rebuilt_transactions,
        )

    async def _recalculate_current_history(
        self,
        *,
        transaction: BookedTransaction,
        current_state: PositionRecalculationState,
    ) -> tuple[PositionHistoryRecord, ...]:
        transaction_date = transaction.transaction_date.date()
        message_epoch = transaction.epoch if transaction.epoch is not None else current_state.epoch
        await self._repository.acquire_replay_lock(
            portfolio_id=transaction.portfolio_id,
            security_id=transaction.security_id,
            epoch=message_epoch,
        )
        await self._repository.delete_records_from(
            portfolio_id=transaction.portfolio_id,
            security_id=transaction.security_id,
            position_date=transaction_date,
            epoch=message_epoch,
        )
        anchor = await self._repository.last_record_before(
            portfolio_id=transaction.portfolio_id,
            security_id=transaction.security_id,
            position_date=transaction_date,
            epoch=message_epoch,
        )
        transactions = await self._repository.list_transactions_from(
            portfolio_id=transaction.portfolio_id,
            security_id=transaction.security_id,
            transaction_date=transaction_date,
        )
        return await self._stage_history(
            anchor=anchor,
            transactions=transactions,
            state=replace(current_state, epoch=message_epoch),
            transaction_date=transaction_date,
        )

    async def _stage_history(
        self,
        *,
        anchor: PositionHistoryRecord | None,
        transactions: tuple[BookedTransaction, ...],
        state: PositionRecalculationState,
        transaction_date: date,
    ) -> tuple[PositionHistoryRecord, ...]:
        records = build_position_history(
            anchor=anchor,
            transactions=transactions,
            epoch=state.epoch,
        )
        if records:
            await self._repository.save_records(records)
            watermark_date = transaction_date - timedelta(days=1)
            if await self._state_store.rearm_generation(
                portfolio_id=state.portfolio_id,
                security_id=state.security_id,
                watermark_date=watermark_date,
            ):
                self._observer.generation_rearmed(
                    portfolio_id=state.portfolio_id,
                    security_id=state.security_id,
                    epoch=state.epoch,
                    transaction_date=transaction_date,
                    watermark_date=watermark_date,
                )
        self._observer.records_staged(epoch=state.epoch, record_count=len(records))
        return records
