"""Persistence ports required by the position-timeseries application use case."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date
from typing import Protocol, TypeVar

from ..domain.position_timeseries.models import (
    PositionCashflowRecord,
    PositionSnapshotRecord,
    PositionTimeseriesRecord,
)

T = TypeVar("T")


class PositionTimeseriesRepository(Protocol):
    """Expose domain records and durable effects without framework objects."""

    async def get_position_snapshot(
        self,
        snapshot_id: int,
        *,
        fallback_epoch: int,
    ) -> PositionSnapshotRecord | None: ...

    async def get_position_timeseries(
        self,
        portfolio_id: str,
        security_id: str,
        a_date: date,
        epoch: int,
    ) -> PositionTimeseriesRecord | None: ...

    async def get_position_timeseries_for_dates(
        self,
        portfolio_id: str,
        security_id: str,
        dates: list[date],
        epoch: int,
    ) -> dict[date, PositionTimeseriesRecord]: ...

    async def upsert_position_timeseries(
        self,
        record: PositionTimeseriesRecord,
    ) -> None: ...

    async def get_all_cashflows_for_security_date(
        self,
        portfolio_id: str,
        security_id: str,
        a_date: date,
        epoch: int,
    ) -> list[PositionCashflowRecord]: ...

    async def get_last_snapshot_before(
        self,
        portfolio_id: str,
        security_id: str,
        a_date: date,
        epoch: int,
    ) -> PositionSnapshotRecord | None: ...

    async def get_next_snapshots_after(
        self,
        portfolio_id: str,
        security_id: str,
        a_date: date,
        epoch: int,
        limit: int,
    ) -> list[PositionSnapshotRecord]: ...

    async def get_cashflows_for_security_dates(
        self,
        portfolio_id: str,
        security_id: str,
        dates: list[date],
        epoch: int,
    ) -> dict[date, list[PositionCashflowRecord]]: ...

    async def stage_aggregation_jobs(
        self,
        portfolio_id: str,
        aggregation_dates: list[date],
        correlation_id: str | None,
    ) -> None: ...


class PositionTimeseriesRepositoryProvider(Protocol):
    """Run one application operation inside a durable transaction boundary."""

    async def run_in_transaction(
        self,
        operation: Callable[[PositionTimeseriesRepository], Awaitable[T]],
    ) -> T: ...
