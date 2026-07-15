"""Stage portfolio aggregation completion through an application-owned port."""

from __future__ import annotations

from ...domain.portfolio_timeseries.models import PortfolioAggregationCompletion
from ...ports.aggregation_completion import AggregationCompletionEventStager


class StagePortfolioAggregationCompletion:
    """Record the durable events implied by a completed portfolio aggregation."""

    def __init__(self, *, event_stager: AggregationCompletionEventStager) -> None:
        self._event_stager = event_stager

    async def execute(
        self,
        completion: PortfolioAggregationCompletion,
        *,
        correlation_id: str | None,
    ) -> None:
        """Stage completion and reconciliation events in the caller's transaction."""

        await self._event_stager.stage_completion(
            completion,
            correlation_id=correlation_id,
        )
