from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Protocol

from portfolio_common.database_models import (
    FinancialReconciliationFinding,
    FinancialReconciliationRun,
    PortfolioTimeseries,
)
from portfolio_common.domain.tenant import TenantId


@dataclass(frozen=True, slots=True, order=True)
class FxRateLookupKey:
    """Normalized point-in-time FX evidence requested by reconciliation."""

    from_currency: str
    to_currency: str
    business_date: date


class ReconciliationRunWriter(Protocol):
    async def reconciliation_scope_exists(
        self,
        *,
        tenant_id: TenantId,
        portfolio_id: str | None,
    ) -> bool: ...

    async def create_run(
        self,
        *,
        tenant_id: TenantId,
        reconciliation_type: str,
        portfolio_id: str | None,
        business_date: date | None,
        epoch: int | None,
        aggregation_revision: int | None,
        requested_by: str | None,
        dedupe_key: str | None,
        correlation_id: str | None,
        tolerance: Decimal | None,
    ) -> tuple[FinancialReconciliationRun, bool]: ...

    async def add_findings(
        self,
        *,
        tenant_id: TenantId,
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
        tenant_id: TenantId,
        portfolio_id: str | None,
        business_date: date | None,
    ) -> Any: ...


class PositionValuationEvidenceReader(Protocol):
    async def fetch_position_valuation_rows(
        self,
        *,
        tenant_id: TenantId,
        portfolio_id: str | None,
        business_date: date | None,
        epoch: int | None,
    ) -> Any: ...


class TimeseriesIntegrityEvidenceReader(Protocol):
    async def fetch_portfolio_timeseries_rows(
        self,
        *,
        tenant_id: TenantId,
        portfolio_id: str | None,
        business_date: date | None,
        epoch: int | None,
    ) -> list[PortfolioTimeseries]: ...

    async def fetch_position_timeseries_aggregates(
        self,
        *,
        tenant_id: TenantId,
        portfolio_id: str | None,
        business_date: date | None,
        epoch: int | None,
    ) -> Any: ...

    async def fetch_snapshot_counts(
        self,
        *,
        tenant_id: TenantId,
        portfolio_id: str | None,
        business_date: date | None,
        epoch: int | None,
    ) -> Any: ...

    async def fetch_authoritative_position_timeseries_rows(
        self,
        *,
        tenant_id: TenantId,
        portfolio_id: str,
        business_date: date,
        epoch: int,
    ) -> Any: ...

    async def fetch_authoritative_snapshot_count(
        self,
        *,
        tenant_id: TenantId,
        portfolio_id: str,
        business_date: date,
        epoch: int,
    ) -> int: ...

    async def fetch_latest_fx_rates(
        self,
        *,
        keys: Sequence[FxRateLookupKey],
    ) -> dict[FxRateLookupKey, Decimal | None]: ...


class ReconciliationRepositoryPort(
    ReconciliationRunWriter,
    TransactionCashflowEvidenceReader,
    PositionValuationEvidenceReader,
    TimeseriesIntegrityEvidenceReader,
    Protocol,
):
    """Complete transitional port consumed by the current reconciliation service."""
