from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any, Protocol

from portfolio_common.database_models import (
    FinancialReconciliationFinding,
    FinancialReconciliationRun,
    FxRate,
    PortfolioTimeseries,
)


class ReconciliationRunWriter(Protocol):
    async def create_run(
        self,
        *,
        reconciliation_type: str,
        portfolio_id: str | None,
        business_date: date | None,
        epoch: int | None,
        requested_by: str | None,
        dedupe_key: str | None,
        correlation_id: str | None,
        tolerance: Decimal | None,
    ) -> tuple[FinancialReconciliationRun, bool]: ...

    async def add_findings(
        self,
        findings: Sequence[FinancialReconciliationFinding],
    ) -> None: ...

    async def mark_run_completed(
        self,
        run: FinancialReconciliationRun,
        *,
        status: str,
        summary: dict,
        failure_reason: str | None = None,
    ) -> None: ...


class TransactionCashflowEvidenceReader(Protocol):
    async def fetch_transaction_cashflow_rows(
        self,
        *,
        portfolio_id: str | None,
        business_date: date | None,
    ) -> Any: ...


class PositionValuationEvidenceReader(Protocol):
    async def fetch_position_valuation_rows(
        self,
        *,
        portfolio_id: str | None,
        business_date: date | None,
        epoch: int | None,
    ) -> Any: ...


class TimeseriesIntegrityEvidenceReader(Protocol):
    async def fetch_portfolio_timeseries_rows(
        self,
        *,
        portfolio_id: str | None,
        business_date: date | None,
        epoch: int | None,
    ) -> list[PortfolioTimeseries]: ...

    async def fetch_position_timeseries_aggregates(
        self,
        *,
        portfolio_id: str | None,
        business_date: date | None,
        epoch: int | None,
    ) -> Any: ...

    async def fetch_snapshot_counts(
        self,
        *,
        portfolio_id: str | None,
        business_date: date | None,
        epoch: int | None,
    ) -> Any: ...

    async def fetch_authoritative_position_timeseries_rows(
        self,
        *,
        portfolio_id: str,
        business_date: date,
        epoch: int,
    ) -> Any: ...

    async def fetch_authoritative_snapshot_count(
        self,
        *,
        portfolio_id: str,
        business_date: date,
        epoch: int,
    ) -> int: ...

    async def fetch_latest_fx_rate(
        self,
        *,
        from_currency: str,
        to_currency: str,
        business_date: date,
    ) -> FxRate | None: ...


class ReconciliationRepositoryPort(
    ReconciliationRunWriter,
    TransactionCashflowEvidenceReader,
    PositionValuationEvidenceReader,
    TimeseriesIntegrityEvidenceReader,
    Protocol,
):
    """Complete transitional port consumed by the current reconciliation service."""
