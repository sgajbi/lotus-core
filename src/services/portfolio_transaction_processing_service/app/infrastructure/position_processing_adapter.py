"""Adapt position-history application results to the transaction-processing port."""

from __future__ import annotations

from ..application.position_history import PositionHistoryProcessor
from ..domain import BookedTransaction
from ..ports import PositionProcessingResult


class PositionHistoryProcessingAdapter:
    """Expose canonical position-history materialization through the unified port."""

    def __init__(
        self,
        *,
        processor: PositionHistoryProcessor,
    ) -> None:
        self._processor = processor

    async def process(
        self,
        transaction: BookedTransaction,
        *,
        correlation_id: str | None,
        traceparent: str | None,
        rebuild_existing: bool = False,
    ) -> PositionProcessingResult:
        result = await self._processor.process(
            transaction,
            rebuild_existing=rebuild_existing,
        )
        return PositionProcessingResult(
            position_record_count=result.position_record_count,
            replay_queued=False,
            cashflow_rebuild_transactions=result.rebuilt_transactions,
        )
