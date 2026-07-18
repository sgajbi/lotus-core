"""Source-read port required by the Core portfolio snapshot application."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from portfolio_common.domain.holdings_reconciliation import (
    FinancialReconciliationControl,
    HoldingsReconciliationScope,
)

from ..domain.core_snapshot import (
    CoreSnapshotFxRate,
    CoreSnapshotInstrument,
    CoreSnapshotMarketPrice,
    CoreSnapshotPortfolio,
    CoreSnapshotPositionSource,
)


class CoreSnapshotSourceReader(Protocol):
    """Read portfolio state and reference evidence without exposing persistence models."""

    async def get_portfolio(self, portfolio_id: str) -> CoreSnapshotPortfolio | None: ...

    async def get_position_snapshot(
        self, *, portfolio_id: str, as_of_date: date
    ) -> list[CoreSnapshotPositionSource]: ...

    async def get_position_history(
        self, *, portfolio_id: str, as_of_date: date
    ) -> list[CoreSnapshotPositionSource]: ...

    async def get_financial_reconciliation_controls(
        self,
        *,
        portfolio_id: str,
        scopes: tuple[HoldingsReconciliationScope, ...],
    ) -> list[FinancialReconciliationControl]: ...

    async def get_instruments(self, security_ids: list[str]) -> list[CoreSnapshotInstrument]: ...

    async def get_prices(
        self, *, security_id: str, end_date: date
    ) -> list[CoreSnapshotMarketPrice]: ...

    async def get_fx_rates(
        self,
        *,
        from_currency: str,
        to_currency: str,
        start_date: date,
        end_date: date,
    ) -> list[CoreSnapshotFxRate]: ...
