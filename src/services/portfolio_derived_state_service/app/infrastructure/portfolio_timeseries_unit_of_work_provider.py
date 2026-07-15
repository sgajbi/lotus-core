"""SQLAlchemy transaction provider for portfolio-timeseries materialization."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from portfolio_common.db import get_async_db_session
from portfolio_common.outbox_repository import OutboxRepository

from ..ports.aggregation_completion import AggregationCompletionEventStager
from ..ports.portfolio_timeseries import PortfolioTimeseriesRepository
from .aggregation_completion_event_stager import (
    TransactionalAggregationCompletionEventStager,
)
from .portfolio_aggregation_repository import PortfolioAggregationRepository

T = TypeVar("T")


class SqlAlchemyPortfolioTimeseriesUnitOfWorkProvider:
    """Compose aggregation persistence and outbox staging in one transaction."""

    async def run_in_transaction(
        self,
        operation: Callable[
            [PortfolioTimeseriesRepository, AggregationCompletionEventStager],
            Awaitable[T],
        ],
    ) -> T:
        async for session in get_async_db_session():
            async with session.begin():
                repository = PortfolioAggregationRepository(session)
                event_stager = TransactionalAggregationCompletionEventStager(
                    OutboxRepository(session)
                )
                return await operation(repository, event_stager)
        raise RuntimeError("No portfolio-timeseries database session was provided.")
