"""Define framework-neutral ports for position-history materialization."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Protocol

from ..domain import BookedTransaction, PositionHistoryRecord, PositionRecalculationState


class PositionRecalculationReason(StrEnum):
    """Classify position recalculation coordination decisions."""

    ALREADY_MATERIALIZED = "already_materialized"
    BACKDATED_TRANSACTION = "backdated_transaction"
    STALE_EPOCH = "stale_epoch"


class PositionReplayMode(StrEnum):
    """Classify position replay work-depth observations."""

    COALESCED = "coalesced"
    INLINE_REBUILD = "inline_rebuild"


class PositionHistoryRepository(Protocol):
    """Load and persist canonical transaction-backed position history."""

    async def latest_completed_snapshot_date(
        self, *, portfolio_id: str, security_id: str, epoch: int
    ) -> date | None: ...

    async def latest_history_date(
        self, *, portfolio_id: str, security_id: str, epoch: int
    ) -> date | None: ...

    async def contains_transaction(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        transaction_id: str,
        epoch: int,
    ) -> bool: ...

    async def acquire_replay_lock(
        self, *, portfolio_id: str, security_id: str, epoch: int
    ) -> None: ...

    async def list_all_transactions(
        self, *, portfolio_id: str, security_id: str
    ) -> tuple[BookedTransaction, ...]: ...

    async def last_record_before(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        position_date: date,
        epoch: int,
    ) -> PositionHistoryRecord | None: ...

    async def list_transactions_from(
        self, *, portfolio_id: str, security_id: str, transaction_date: date
    ) -> tuple[BookedTransaction, ...]: ...

    async def delete_records_from(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        position_date: date,
        epoch: int,
    ) -> int: ...

    async def save_records(self, records: tuple[PositionHistoryRecord, ...]) -> None: ...


class PositionRecalculationStateStore(Protocol):
    """Coordinate position dirty windows and compare-and-set epochs."""

    async def get_or_create(
        self, *, portfolio_id: str, security_id: str
    ) -> PositionRecalculationState: ...

    async def advance_epoch(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        expected_epoch: int,
        watermark_date: date,
    ) -> PositionRecalculationState | None: ...

    async def rearm_generation(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        watermark_date: date,
    ) -> bool: ...


class PositionEpochFence(Protocol):
    """Reject stale position commands before materialization begins."""

    async def is_current(self, transaction: BookedTransaction) -> bool: ...


class PositionHistoryObserver(Protocol):
    """Observe position recalculation without coupling application policy to telemetry."""

    def backdated_recalculation_detected(
        self,
        *,
        transaction: BookedTransaction,
        current_state: PositionRecalculationState,
        effective_completed_date: date,
        latest_history_date: date | None,
    ) -> None: ...

    def recalculation_coalesced(
        self,
        *,
        transaction: BookedTransaction,
        epoch: int,
        reason: PositionRecalculationReason,
    ) -> None: ...

    def epoch_advanced(
        self,
        *,
        transaction: BookedTransaction,
        state: PositionRecalculationState,
    ) -> None: ...

    def replay_work_items(self, *, mode: PositionReplayMode, count: int) -> None: ...

    def history_rebuilt(
        self,
        *,
        transaction: BookedTransaction,
        epoch: int,
        record_count: int,
        earliest_transaction_date: date,
    ) -> None: ...

    def records_staged(self, *, epoch: int, record_count: int) -> None: ...

    def generation_rearmed(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        epoch: int,
        transaction_date: date,
        watermark_date: date,
    ) -> None: ...
