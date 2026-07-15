"""Application port for portfolio aggregation completion events."""

from __future__ import annotations

from typing import Protocol

from ..domain.portfolio_timeseries.models import PortfolioAggregationCompletion


class AggregationCompletionEventStager(Protocol):
    """Stage all durable events required after portfolio aggregation."""

    async def stage_completion(
        self,
        completion: PortfolioAggregationCompletion,
        *,
        correlation_id: str | None,
    ) -> None: ...
