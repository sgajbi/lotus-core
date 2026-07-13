"""Emit position-history metrics and support logs without risking financial writes."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date

from portfolio_common.logging_utils import operation_log_extra
from portfolio_common.monitoring import (
    EPOCH_MISMATCH_DROPPED_TOTAL,
    POSITION_RECALCULATION_COORDINATION_TOTAL,
    POSITION_RECALCULATION_WORK_ITEMS,
    REPROCESSING_EPOCH_BUMPED_TOTAL,
)

from ..domain.booked_transaction import BookedTransaction
from ..domain.position_history import PositionRecalculationState
from ..ports.position_history import PositionRecalculationReason, PositionReplayMode

logger = logging.getLogger(__name__)


class PrometheusPositionHistoryObserver:
    """Preserve position metrics and logs behind a failure-contained adapter."""

    def stale_epoch_discarded(
        self,
        *,
        transaction: BookedTransaction,
        current_epoch: int,
    ) -> None:
        """Record a stale command without performing a second state-store read."""
        self._record(
            "stale_epoch_discarded",
            lambda: self._record_stale_epoch(
                transaction=transaction,
                current_epoch=current_epoch,
            ),
        )

    def backdated_recalculation_detected(
        self,
        *,
        transaction: BookedTransaction,
        current_state: PositionRecalculationState,
        effective_completed_date: date,
        latest_history_date: date | None,
    ) -> None:
        """Record detection of a backdated transaction and its dirty window."""
        self._record(
            "backdated_recalculation_detected",
            lambda: logger.warning(
                "Back-dated transaction detected. Advancing position recovery epoch.",
                extra=operation_log_extra(
                    event_name="position_backdated_recalculation_detected",
                    operation="materialize_position_history",
                    status="detected",
                    reason_code="backdated_transaction",
                    portfolio_id=transaction.portfolio_id,
                    security_id=transaction.security_id,
                    transaction_date=transaction.transaction_date.date().isoformat(),
                    effective_completed_date=effective_completed_date.isoformat(),
                    watermark_date=current_state.watermark_date.isoformat(),
                    latest_position_history_date=latest_history_date.isoformat()
                    if latest_history_date
                    else None,
                    current_epoch=current_state.epoch,
                    backdated_handling="inline_rebuild",
                ),
            ),
        )

    def recalculation_coalesced(
        self,
        *,
        transaction: BookedTransaction,
        epoch: int,
        reason: PositionRecalculationReason,
    ) -> None:
        """Record a duplicate or stale backdated recalculation trigger."""
        self._record(
            "recalculation_coalesced",
            lambda: self._record_coalesced(
                transaction=transaction,
                epoch=epoch,
                reason=reason,
            ),
        )

    def epoch_advanced(
        self,
        *,
        transaction: BookedTransaction,
        state: PositionRecalculationState,
    ) -> None:
        """Record successful compare-and-set advancement for backdated recovery."""
        self._record(
            "epoch_advanced",
            lambda: self._record_epoch_advanced(transaction=transaction, state=state),
        )

    def replay_work_items(self, *, mode: PositionReplayMode, count: int) -> None:
        """Record replay work depth for capacity and coalescing diagnostics."""
        self._record(
            "replay_work_items",
            lambda: POSITION_RECALCULATION_WORK_ITEMS.labels(mode=mode.value).observe(count),
        )

    def history_rebuilt(
        self,
        *,
        transaction: BookedTransaction,
        epoch: int,
        record_count: int,
        earliest_transaction_date: date,
    ) -> None:
        """Record completion of an atomic backdated history rebuild."""
        self._record(
            "history_rebuilt",
            lambda: logger.info(
                "Rebuilt backdated position history atomically in the new epoch.",
                extra=operation_log_extra(
                    event_name="position_history_rebuilt",
                    operation="materialize_position_history",
                    status="succeeded",
                    reason_code="backdated_transaction",
                    portfolio_id=transaction.portfolio_id,
                    security_id=transaction.security_id,
                    epoch=epoch,
                    position_record_count=record_count,
                    earliest_transaction_date=earliest_transaction_date.isoformat(),
                ),
            ),
        )

    def records_staged(self, *, epoch: int, record_count: int) -> None:
        """Record position-history rows staged in the caller-owned transaction."""
        self._record(
            "records_staged",
            lambda: logger.info(
                "Staged position history records for the recalculation epoch.",
                extra=operation_log_extra(
                    event_name="position_history_staged",
                    operation="materialize_position_history",
                    status="succeeded",
                    reason_code="records_staged",
                    epoch=epoch,
                    position_record_count=record_count,
                ),
            ),
        )

    def generation_rearmed(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        epoch: int,
        transaction_date: date,
        watermark_date: date,
    ) -> None:
        """Record that valuation and timeseries generation were marked dirty."""
        self._record(
            "generation_rearmed",
            lambda: logger.info(
                "Re-armed valuation and timeseries generation after position history write.",
                extra=operation_log_extra(
                    event_name="position_generation_rearmed",
                    operation="materialize_position_history",
                    status="succeeded",
                    reason_code="position_history_changed",
                    portfolio_id=portfolio_id,
                    security_id=security_id,
                    epoch=epoch,
                    transaction_date=transaction_date.isoformat(),
                    new_watermark_date=watermark_date.isoformat(),
                ),
            ),
        )

    @staticmethod
    def _record_coalesced(
        *,
        transaction: BookedTransaction,
        epoch: int,
        reason: PositionRecalculationReason,
    ) -> None:
        POSITION_RECALCULATION_COORDINATION_TOTAL.labels(
            outcome="coalesced",
            reason=reason.value,
        ).inc()
        if reason is PositionRecalculationReason.STALE_EPOCH:
            logger.warning(
                "Skipping back-dated replay because the epoch fence is stale.",
                extra=operation_log_extra(
                    event_name="position_recalculation_coalesced",
                    operation="materialize_position_history",
                    status="skipped",
                    reason_code="stale_epoch",
                    portfolio_id=transaction.portfolio_id,
                    security_id=transaction.security_id,
                    expected_epoch=epoch,
                    transaction_id=transaction.transaction_id,
                ),
            )
            return
        logger.info(
            "Coalesced backdated position trigger already materialized in current epoch.",
            extra=operation_log_extra(
                event_name="position_recalculation_coalesced",
                operation="materialize_position_history",
                status="skipped",
                reason_code="already_materialized",
                portfolio_id=transaction.portfolio_id,
                security_id=transaction.security_id,
                transaction_id=transaction.transaction_id,
                epoch=epoch,
            ),
        )

    @staticmethod
    def _record_stale_epoch(
        *,
        transaction: BookedTransaction,
        current_epoch: int,
    ) -> None:
        message_epoch = transaction.epoch if transaction.epoch is not None else current_epoch
        EPOCH_MISMATCH_DROPPED_TOTAL.labels(
            service_name="position-calculator",
            topic="<unknown>",
        ).inc()
        logger.warning(
            "Position command has stale epoch. Discarding.",
            extra=operation_log_extra(
                event_name="position_command_discarded",
                operation="materialize_position_history",
                status="skipped",
                reason_code="stale_epoch",
                portfolio_id=transaction.portfolio_id,
                security_id=transaction.security_id,
                transaction_id=transaction.transaction_id,
                message_epoch=message_epoch,
                current_epoch=current_epoch,
            ),
        )

    @staticmethod
    def _record_epoch_advanced(
        *,
        transaction: BookedTransaction,
        state: PositionRecalculationState,
    ) -> None:
        REPROCESSING_EPOCH_BUMPED_TOTAL.labels(trigger="backdated_transaction").inc()
        POSITION_RECALCULATION_COORDINATION_TOTAL.labels(
            outcome="epoch_advanced",
            reason=PositionRecalculationReason.BACKDATED_TRANSACTION.value,
        ).inc()

    @staticmethod
    def _record(operation: str, callback: Callable[[], object]) -> None:
        try:
            callback()
        except Exception:
            logger.exception(
                "Position history telemetry observation failed.",
                extra=operation_log_extra(
                    event_name="position_history_observation_failed",
                    operation="observe_position_history",
                    status="failed",
                    reason_code="telemetry_error",
                    position_observation=operation,
                ),
            )


PROMETHEUS_POSITION_HISTORY_OBSERVER = PrometheusPositionHistoryObserver()
