"""Application tests for portfolio aggregation completion staging."""

from datetime import date

import pytest

from src.services.portfolio_derived_state_service.app.application.portfolio_timeseries import (
    stage_aggregation_completion,
)
from src.services.portfolio_derived_state_service.app.domain.portfolio_timeseries.models import (
    PortfolioAggregationCompletion,
)

pytestmark = pytest.mark.asyncio


class _CompletionEventStager:
    def __init__(self) -> None:
        self.calls: list[tuple[PortfolioAggregationCompletion, str | None]] = []

    async def stage_completion(
        self,
        completion: PortfolioAggregationCompletion,
        *,
        correlation_id: str | None,
    ) -> None:
        self.calls.append((completion, correlation_id))


async def test_use_case_delegates_domain_completion_to_event_port() -> None:
    stager = _CompletionEventStager()
    use_case = stage_aggregation_completion.StagePortfolioAggregationCompletion(event_stager=stager)
    completion = PortfolioAggregationCompletion(
        portfolio_id="PORT-1",
        aggregation_date=date(2026, 7, 15),
        epoch=4,
        aggregation_revision=7,
    )

    await use_case.execute(completion, correlation_id="corr-1")

    assert stager.calls == [(completion, "corr-1")]
