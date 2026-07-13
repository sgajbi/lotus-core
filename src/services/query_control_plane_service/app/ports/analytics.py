"""Ports required by the analytics input and export application capability."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import AsyncContextManager, Protocol

from ..domain.analytics import (
    AnalyticsCashflowEvidence,
    AnalyticsExportJobRecord,
    PortfolioAnalyticsSource,
    PositionValuationObservation,
    PriorPositionValuation,
)


class AnalyticsTimeseriesReader(Protocol):
    """Read source portfolio, timeseries, cashflow, calendar, and FX evidence."""

    async def get_portfolio(self, portfolio_id: str) -> PortfolioAnalyticsSource | None: ...

    async def get_latest_portfolio_timeseries_date(self, portfolio_id: str) -> date | None: ...

    async def get_latest_position_timeseries_date(self, portfolio_id: str) -> date | None: ...

    async def list_business_dates(self, *, start_date: date, end_date: date) -> list[date]: ...

    async def list_position_timeseries_rows(
        self,
        *,
        portfolio_id: str,
        start_date: date,
        end_date: date,
        page_size: int,
        cursor_date: date | None,
        cursor_security_id: str | None,
        security_ids: list[str],
        position_ids: list[str],
        dimension_filters: dict[str, set[str]],
        snapshot_epoch: int | None = None,
    ) -> list[PositionValuationObservation]: ...

    async def list_position_timeseries_rows_unpaged(
        self,
        *,
        portfolio_id: str,
        start_date: date,
        end_date: date,
        snapshot_epoch: int | None = None,
    ) -> list[PositionValuationObservation]: ...

    async def list_position_observation_dates(
        self,
        *,
        portfolio_id: str,
        start_date: date,
        end_date: date,
        snapshot_epoch: int | None = None,
    ) -> list[date]: ...

    async def list_latest_position_timeseries_before(
        self,
        *,
        portfolio_id: str,
        before_date: date,
        security_ids: list[str],
        snapshot_epoch: int | None = None,
    ) -> list[PriorPositionValuation]: ...

    async def list_position_cashflow_rows(
        self,
        *,
        portfolio_id: str,
        security_ids: list[str],
        valuation_dates: list[date],
        snapshot_epoch: int | None = None,
    ) -> list[AnalyticsCashflowEvidence]: ...

    async def list_portfolio_cashflow_rows(
        self,
        *,
        portfolio_id: str,
        valuation_dates: list[date],
        snapshot_epoch: int | None = None,
    ) -> list[AnalyticsCashflowEvidence]: ...

    async def get_position_snapshot_epoch(
        self,
        *,
        portfolio_id: str,
        start_date: date,
        end_date: date,
        security_ids: list[str],
        position_ids: list[str],
        dimension_filters: dict[str, set[str]],
    ) -> int: ...

    async def get_fx_rates_map(
        self,
        *,
        from_currency: str,
        to_currency: str,
        start_date: date,
        end_date: date,
    ) -> dict[date, Decimal]: ...


class AnalyticsExportStore(Protocol):
    """Persist and transition durable analytics export jobs."""

    async def create_job(
        self,
        *,
        job_id: str,
        dataset_type: str,
        portfolio_id: str,
        request_fingerprint: str,
        request_payload: dict[str, object],
        result_format: str,
        compression: str,
    ) -> AnalyticsExportJobRecord: ...

    async def get_job(self, job_id: str) -> AnalyticsExportJobRecord | None: ...

    async def get_latest_by_fingerprint(
        self,
        *,
        request_fingerprint: str,
        dataset_type: str,
    ) -> AnalyticsExportJobRecord | None: ...

    async def mark_running(self, row: AnalyticsExportJobRecord) -> AnalyticsExportJobRecord: ...

    async def mark_completed(
        self,
        row: AnalyticsExportJobRecord,
        *,
        result_payload: dict[str, object],
        result_row_count: int,
    ) -> AnalyticsExportJobRecord: ...

    async def mark_failed(
        self, row: AnalyticsExportJobRecord, *, error_message: str
    ) -> AnalyticsExportJobRecord: ...


class AnalyticsUnitOfWork(Protocol):
    """Own one atomic analytics export lifecycle transition."""

    def transaction(self) -> AsyncContextManager[None]: ...
