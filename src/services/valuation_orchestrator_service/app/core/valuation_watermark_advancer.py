import logging
from typing import Any, Dict, List

from portfolio_common.logging_utils import operation_log_extra
from portfolio_common.monitoring import (
    REPROCESSING_ACTIVE_KEYS_TOTAL,
    observe_reprocessing_stale_skips,
)
from portfolio_common.position_state_repository import PositionStateRepository

from ..repositories.valuation_repository import ValuationRepository

logger = logging.getLogger(__name__)


class ValuationWatermarkAdvancer:
    """Advances valuation watermarks based on contiguous valuation snapshots."""

    def __init__(self, *, batch_size: int) -> None:
        self._batch_size = batch_size

    @staticmethod
    def _build_terminal_reprocessing_updates(states) -> List[Dict[str, Any]]:
        return [
            {
                "portfolio_id": state.portfolio_id,
                "security_id": state.security_id,
                "expected_epoch": state.epoch,
                "watermark_date": state.watermark_date,
                "status": "CURRENT",
            }
            for state in states
        ]

    @staticmethod
    def _build_watermark_advance_updates(
        states,
        advancable_dates: Dict[tuple[str, str], Any],
        latest_business_date,
    ) -> List[Dict[str, Any]]:
        updates_to_commit: List[Dict[str, Any]] = []
        for state in states:
            key = (state.portfolio_id, state.security_id)
            new_watermark = advancable_dates.get(key)

            if new_watermark and new_watermark > state.watermark_date:
                is_complete = new_watermark == latest_business_date
                updates_to_commit.append(
                    {
                        "portfolio_id": state.portfolio_id,
                        "security_id": state.security_id,
                        "expected_epoch": state.epoch,
                        "watermark_date": new_watermark,
                        "status": "CURRENT" if is_complete else state.status,
                    }
                )
        return updates_to_commit

    @staticmethod
    async def _bulk_update_watermark_states(
        position_state_repo: PositionStateRepository,
        updates: List[Dict[str, Any]],
        *,
        stale_skip_reason: str,
        warning_message: str,
        success_message: str,
        success_extra_key: str,
    ) -> int:
        if not updates:
            return 0

        updated_count = int(await position_state_repo.bulk_update_states(updates))
        stale_skipped_count = len(updates) - updated_count

        if stale_skipped_count:
            observe_reprocessing_stale_skips(stale_skip_reason, stale_skipped_count)
            logger.warning(
                warning_message,
                extra=operation_log_extra(
                    event_name="valuation.scheduler.watermark_bulk_update_partial",
                    operation="valuation.scheduler.advance_watermarks",
                    status="partial",
                    reason_code=stale_skip_reason,
                    prepared_count=len(updates),
                    updated_count=updated_count,
                    stale_skipped_count=stale_skipped_count,
                ),
            )
        elif updated_count:
            logger.info(
                success_message,
                extra=operation_log_extra(
                    event_name="valuation.scheduler.watermark_bulk_update_completed",
                    operation="valuation.scheduler.advance_watermarks",
                    status="succeeded",
                    reason_code="watermark_update_completed",
                    **{success_extra_key: updated_count},
                ),
            )

        return updated_count

    async def _normalize_terminal_reprocessing_states(
        self,
        position_state_repo: PositionStateRepository,
        terminal_reprocessing_states,
    ) -> None:
        terminal_updates = self._build_terminal_reprocessing_updates(terminal_reprocessing_states)
        await self._bulk_update_watermark_states(
            position_state_repo,
            terminal_updates,
            stale_skip_reason="terminal_reprocessing_normalization",
            warning_message=(
                "ValuationScheduler normalized fewer terminal reprocessing states than "
                "prepared updates."
            ),
            success_message="ValuationScheduler normalized terminal reprocessing states.",
            success_extra_key="normalized_count",
        )

    async def _advance_lagging_watermark_states(
        self,
        repo: ValuationRepository,
        position_state_repo: PositionStateRepository,
        *,
        lagging_states,
        first_open_dates,
        latest_business_date,
    ) -> None:
        advancable_dates = await repo.find_contiguous_snapshot_dates(
            lagging_states, first_open_dates
        )
        updates_to_commit = self._build_watermark_advance_updates(
            lagging_states,
            advancable_dates,
            latest_business_date,
        )
        await self._bulk_update_watermark_states(
            position_state_repo,
            updates_to_commit,
            stale_skip_reason="watermark_advance",
            warning_message="ValuationScheduler advanced fewer watermarks than prepared updates.",
            success_message="ValuationScheduler advanced watermarks.",
            success_extra_key="updated_count",
        )

    async def _load_watermark_advance_inputs(
        self, repo: ValuationRepository
    ) -> tuple[Any, list[Any], list[Any], Dict[tuple[str, str, int], Any]] | None:
        latest_business_date = await repo.get_latest_business_date()
        if not latest_business_date:
            return None

        lagging_states = await repo.get_lagging_states(latest_business_date, self._batch_size)
        terminal_reprocessing_states = await repo.get_terminal_reprocessing_states(
            latest_business_date, self._batch_size
        )
        lagging_keys = [(s.portfolio_id, s.security_id, s.epoch) for s in lagging_states]
        first_open_dates = await repo.get_first_open_dates_for_keys(lagging_keys)
        return (
            latest_business_date,
            lagging_states,
            terminal_reprocessing_states,
            first_open_dates,
        )

    @staticmethod
    def _observe_reprocessing_active_keys(
        lagging_states,
        terminal_reprocessing_states,
    ) -> None:
        reprocessing_count = sum(1 for s in lagging_states if s.status == "REPROCESSING") + len(
            terminal_reprocessing_states
        )
        REPROCESSING_ACTIVE_KEYS_TOTAL.set(reprocessing_count)

    async def advance_watermarks(
        self,
        *,
        repo: ValuationRepository,
        position_state_repo: PositionStateRepository,
    ) -> None:
        inputs = await self._load_watermark_advance_inputs(repo)
        if inputs is None:
            return
        (
            latest_business_date,
            lagging_states,
            terminal_reprocessing_states,
            first_open_dates,
        ) = inputs
        self._observe_reprocessing_active_keys(
            lagging_states,
            terminal_reprocessing_states,
        )

        await self._normalize_terminal_reprocessing_states(
            position_state_repo, terminal_reprocessing_states
        )

        if lagging_states:
            await self._advance_lagging_watermark_states(
                repo,
                position_state_repo,
                lagging_states=lagging_states,
                first_open_dates=first_open_dates,
                latest_business_date=latest_business_date,
            )
