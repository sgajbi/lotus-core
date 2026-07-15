"""SQLAlchemy transaction provider for position-timeseries materialization."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from portfolio_common.db import get_async_db_session

from ..ports.position_timeseries import PositionTimeseriesRepository
from .timeseries_generation_repository import TimeseriesGenerationRepository

T = TypeVar("T")


class SqlAlchemyPositionTimeseriesRepositoryProvider:
    """Run one position-timeseries operation in a committed database transaction."""

    async def run_in_transaction(
        self,
        operation: Callable[[PositionTimeseriesRepository], Awaitable[T]],
    ) -> T:
        async for session in get_async_db_session():
            async with session.begin():
                return await operation(TimeseriesGenerationRepository(session))
        raise RuntimeError("No position-timeseries database session was provided.")
