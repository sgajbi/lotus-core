import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

from portfolio_common.logging_utils import operation_log_extra
from portfolio_common.monitoring import (
    POSITION_STATE_WATERMARK_LAG_DAYS,
    SCHEDULER_GAP_DAYS,
    SNAPSHOT_LAG_SECONDS,
    VALUATION_JOBS_CREATED_TOTAL,
)
from portfolio_common.position_state_repository import PositionStateRepository
from portfolio_common.valuation_job_repository import ValuationJobRepository, ValuationJobUpsert

from ..repositories.valuation_repository import ValuationRepository

logger = logging.getLogger(__name__)


class ValuationBackfillPlanner:
    """Plans and stages valuation backfill jobs for lagging position states."""

    def __init__(self, *, backfill_upsert_chunk_size: int) -> None:
        self._backfill_upsert_chunk_size = backfill_upsert_chunk_size

    @staticmethod
    def build_backfill_correlation_id(
        portfolio_id: str,
        security_id: str,
        epoch: int,
        valuation_date,
        watermark_updated_at: datetime | None = None,
    ) -> str:
        base_correlation_id = (
            f"SCHEDULER_BACKFILL:{portfolio_id}:{security_id}:{epoch}:{valuation_date.isoformat()}"
        )
        if watermark_updated_at is None:
            return base_correlation_id
        return f"{base_correlation_id}:{watermark_updated_at.isoformat()}"

    @staticmethod
    def _partition_states_without_position_history(
        states_to_backfill,
        first_open_dates: Dict[tuple[str, str, int], Any],
    ) -> tuple[list[Any], list[Any]]:
        states_to_normalize: list[Any] = []
        states_waiting_for_history: list[Any] = []

        for state in states_to_backfill:
            key = (state.portfolio_id, state.security_id, state.epoch)
            if key in first_open_dates:
                continue
            if state.status == "REPROCESSING":
                states_waiting_for_history.append(state)
            else:
                states_to_normalize.append(state)

        return states_to_normalize, states_waiting_for_history

    @staticmethod
    def _build_no_history_normalization_updates(
        states_to_normalize,
        latest_business_date,
    ) -> List[Dict[str, Any]]:
        return [
            {
                "portfolio_id": state.portfolio_id,
                "security_id": state.security_id,
                "expected_epoch": state.epoch,
                "watermark_date": latest_business_date,
                "status": "CURRENT",
            }
            for state in states_to_normalize
        ]

    async def _normalize_no_history_states(
        self,
        position_state_repo: PositionStateRepository,
        states_to_normalize,
        latest_business_date,
    ) -> None:
        normalized_updates = self._build_no_history_normalization_updates(
            states_to_normalize, latest_business_date
        )
        if not normalized_updates:
            return

        normalized_count = await position_state_repo.bulk_update_states(normalized_updates)
        stale_skipped_count = len(normalized_updates) - normalized_count
        if stale_skipped_count:
            logger.warning(
                "ValuationScheduler normalized fewer no-history states than prepared updates.",
                extra=operation_log_extra(
                    event_name="valuation.scheduler.no_history_normalization_partial",
                    operation="valuation.scheduler.create_backfill_jobs",
                    status="partial",
                    reason_code="no_history_ownership_lost",
                    prepared_count=len(normalized_updates),
                    updated_count=normalized_count,
                    stale_skipped_count=stale_skipped_count,
                ),
            )
        elif normalized_count:
            logger.info(
                "ValuationScheduler normalized no-history states to current watermark.",
                extra=operation_log_extra(
                    event_name="valuation.scheduler.no_history_normalization_completed",
                    operation="valuation.scheduler.create_backfill_jobs",
                    status="succeeded",
                    reason_code="no_history_normalized",
                    normalized_count=normalized_count,
                ),
            )

    @staticmethod
    def _log_no_history_reprocessing_defer(states_waiting_for_history) -> None:
        if not states_waiting_for_history:
            return

        logger.info(
            "ValuationScheduler deferred no-history reprocessing states until "
            "current-epoch position history is visible.",
            extra=operation_log_extra(
                event_name="valuation.scheduler.no_history_deferred",
                operation="valuation.scheduler.create_backfill_jobs",
                status="deferred",
                reason_code="current_epoch_history_missing",
                deferred_count=len(states_waiting_for_history),
            ),
        )

    @staticmethod
    def _observe_backfill_gap_metrics(state, latest_business_date) -> None:
        gap_days = (latest_business_date - state.watermark_date).days
        SCHEDULER_GAP_DAYS.observe(gap_days)
        SNAPSHOT_LAG_SECONDS.observe(gap_days * 86400)
        POSITION_STATE_WATERMARK_LAG_DAYS.set(gap_days)

    @staticmethod
    def _log_missing_current_epoch_history(state, latest_business_date) -> None:
        logger.info(
            "No current-epoch position history found; skipping backfill for now.",
            extra=operation_log_extra(
                event_name="valuation.scheduler.current_epoch_history_missing",
                operation="valuation.scheduler.create_backfill_jobs",
                status="skipped",
                reason_code="current_epoch_history_missing",
                epoch=state.epoch,
                state_status=state.status,
                latest_business_date=str(latest_business_date),
            ),
        )

    def _build_backfill_job_requests(
        self,
        state,
        first_open_date,
        latest_business_date,
    ) -> list[ValuationJobUpsert]:
        start_date = max(state.watermark_date, first_open_date - timedelta(days=1))
        job_requests: list[ValuationJobUpsert] = []
        current_date = start_date + timedelta(days=1)

        while current_date <= latest_business_date:
            job_requests.append(
                ValuationJobUpsert(
                    portfolio_id=state.portfolio_id,
                    security_id=state.security_id,
                    valuation_date=current_date,
                    epoch=state.epoch,
                    correlation_id=self.build_backfill_correlation_id(
                        state.portfolio_id,
                        state.security_id,
                        state.epoch,
                        current_date,
                        state.updated_at,
                    ),
                )
            )
            current_date += timedelta(days=1)

        return job_requests

    def _iter_backfill_job_chunks(
        self,
        states_to_backfill,
        first_open_dates: Dict[tuple[str, str, int], Any],
        latest_business_date,
    ):
        chunk: list[ValuationJobUpsert] = []
        for state in states_to_backfill:
            self._observe_backfill_gap_metrics(state, latest_business_date)
            key = (state.portfolio_id, state.security_id, state.epoch)
            first_open_date = first_open_dates.get(key)

            if not first_open_date:
                self._log_missing_current_epoch_history(state, latest_business_date)
                continue

            job_requests = self._build_backfill_job_requests(
                state, first_open_date, latest_business_date
            )
            if not job_requests:
                continue

            logger.info(
                "Backfill valuation jobs planned for state.",
                extra=operation_log_extra(
                    event_name="valuation.scheduler.backfill_jobs_planned_for_state",
                    operation="valuation.scheduler.create_backfill_jobs",
                    status="succeeded",
                    reason_code="jobs_planned",
                    requested_count=len(job_requests),
                    epoch=state.epoch,
                ),
            )

            for job_request in job_requests:
                chunk.append(job_request)
                if len(chunk) >= self._backfill_upsert_chunk_size:
                    yield chunk
                    chunk = []
        if chunk:
            yield chunk

    async def _stage_backfill_job_chunk(
        self,
        job_repo: ValuationJobRepository,
        job_requests: list[ValuationJobUpsert],
        *,
        chunk_index: int,
    ) -> None:
        staged_count = await job_repo.upsert_jobs(job_requests)
        VALUATION_JOBS_CREATED_TOTAL.labels(job_type="backfill").inc(staged_count)
        logger.info(
            "Backfill valuation jobs staged in bounded chunk.",
            extra=operation_log_extra(
                event_name="valuation.scheduler.backfill_jobs_staged",
                operation="valuation.scheduler.create_backfill_jobs",
                status="succeeded",
                reason_code="jobs_staged",
                staged_count=staged_count,
                requested_count=len(job_requests),
                chunk_index=chunk_index,
                chunk_size_limit=self._backfill_upsert_chunk_size,
            ),
        )

    async def _process_backfill_states(
        self,
        job_repo: ValuationJobRepository,
        states_to_backfill,
        first_open_dates: Dict[tuple[str, str, int], Any],
        latest_business_date,
    ) -> None:
        for chunk_index, job_requests in enumerate(
            self._iter_backfill_job_chunks(
                states_to_backfill,
                first_open_dates,
                latest_business_date,
            )
        ):
            await self._stage_backfill_job_chunk(
                job_repo,
                job_requests,
                chunk_index=chunk_index,
            )

    async def create_backfill_jobs(
        self,
        *,
        repo: ValuationRepository,
        job_repo: ValuationJobRepository,
        position_state_repo: PositionStateRepository,
        batch_size: int,
    ) -> None:
        latest_business_date = await repo.get_latest_business_date()

        if not latest_business_date:
            logger.debug("Scheduler: No business dates found, skipping backfill job creation.")
            return

        states_to_backfill = await repo.get_states_needing_backfill(
            latest_business_date, batch_size
        )

        if not states_to_backfill:
            logger.debug("Scheduler: No keys need backfilling.")
            return

        logger.info(
            "Valuation states needing backfill found.",
            extra=operation_log_extra(
                event_name="valuation.scheduler.backfill_states_found",
                operation="valuation.scheduler.create_backfill_jobs",
                status="started",
                reason_code="backfill_states_found",
                state_count=len(states_to_backfill),
                latest_business_date=str(latest_business_date),
            ),
        )

        keys_to_check = [(s.portfolio_id, s.security_id, s.epoch) for s in states_to_backfill]

        first_open_dates = await repo.get_first_open_dates_for_keys(keys_to_check)
        (
            keys_without_history_to_normalize,
            keys_waiting_for_history,
        ) = self._partition_states_without_position_history(states_to_backfill, first_open_dates)
        await self._normalize_no_history_states(
            position_state_repo,
            keys_without_history_to_normalize,
            latest_business_date,
        )
        self._log_no_history_reprocessing_defer(keys_waiting_for_history)
        await self._process_backfill_states(
            job_repo,
            states_to_backfill,
            first_open_dates,
            latest_business_date,
        )
