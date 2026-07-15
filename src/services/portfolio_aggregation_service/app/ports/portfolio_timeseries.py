"""Application ports required for portfolio-timeseries materialization."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date
from typing import Protocol, TypeVar

from ..domain.aggregation_records import (
    AggregationJobCompletionDisposition,
    PortfolioAggregationScope,
    PortfolioTimeseriesRecord,
    PositionTimeseriesRecord,
)
from .aggregation_completion import AggregationCompletionEventStager
from .timeseries_market_data import TimeseriesMarketDataPort

T = TypeVar("T")


class PortfolioTimeseriesRepository(TimeseriesMarketDataPort, Protocol):
    """Expose aggregation sources and durable effects without framework objects."""

    async def get_portfolio(self, portfolio_id: str) -> PortfolioAggregationScope | None: ...

    async def get_current_epoch_for_portfolio(self, portfolio_id: str) -> int: ...

    async def get_all_position_timeseries_for_date(
        self,
        portfolio_id: str,
        aggregation_date: date,
        epoch: int,
    ) -> list[PositionTimeseriesRecord]: ...

    async def upsert_portfolio_timeseries(self, record: PortfolioTimeseriesRecord) -> None: ...

    async def complete_or_requeue_job(
        self,
        *,
        job_id: int,
        lease_token: str,
    ) -> AggregationJobCompletionDisposition: ...

    async def mark_job_failed(self, *, job_id: int, lease_token: str) -> bool: ...


class PortfolioTimeseriesCalculation(Protocol):
    """Resolve source data and calculate one portfolio-day record."""

    async def calculate_daily_record(
        self,
        portfolio: PortfolioAggregationScope,
        aggregation_date: date,
        epoch: int,
        position_timeseries: list[PositionTimeseriesRecord],
        repository: TimeseriesMarketDataPort,
        /,
    ) -> PortfolioTimeseriesRecord: ...


class PortfolioTimeseriesUnitOfWorkProvider(Protocol):
    """Run one application operation inside a durable transaction boundary."""

    async def run_in_transaction(
        self,
        operation: Callable[
            [PortfolioTimeseriesRepository, AggregationCompletionEventStager],
            Awaitable[T],
        ],
    ) -> T: ...
