"""Application use case for durable FX correction replay jobs."""

from __future__ import annotations

from datetime import date, timedelta

from ..domain.fx_revaluation import DirectCurrencyPair, FxReplayExecution
from ..ports.fx_revaluation import FxRevaluationRepository, PositionWatermarkWriter


class ProcessFxRevaluationJob:
    """Resolve pair impact and reset only affected current position watermarks."""

    def __init__(
        self,
        *,
        repository: FxRevaluationRepository,
        watermarks: PositionWatermarkWriter,
    ) -> None:
        self._repository = repository
        self._watermarks = watermarks

    async def execute(
        self,
        *,
        pair: DirectCurrencyPair,
        earliest_impacted_date: date,
    ) -> FxReplayExecution:
        """Apply one replay job or preserve it when source readiness is incomplete."""
        position_keys = await self._repository.find_affected_position_keys(
            pair=pair,
            earliest_impacted_date=earliest_impacted_date,
        )
        if not position_keys:
            return FxReplayExecution(
                pair=pair,
                earliest_impacted_date=earliest_impacted_date,
                targeted_key_count=0,
                updated_key_count=0,
            )

        updated_count = await self._watermarks.update_watermarks_if_older(
            keys=[(key.portfolio_id, key.security_id) for key in position_keys],
            new_watermark_date=earliest_impacted_date - timedelta(days=1),
        )
        return FxReplayExecution(
            pair=pair,
            earliest_impacted_date=earliest_impacted_date,
            targeted_key_count=len(position_keys),
            updated_key_count=updated_count,
        )
