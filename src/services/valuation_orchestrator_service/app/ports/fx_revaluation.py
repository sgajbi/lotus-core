"""Application ports for FX correction impact and durable scheduling."""

from __future__ import annotations

from datetime import date
from typing import Protocol, Sequence

from ..domain.fx_revaluation import (
    DirectCurrencyPair,
    FxRateCorrection,
    PositionValuationKey,
)


class FxRevaluationRepository(Protocol):
    """Resolve FX impact and persist bounded revaluation intent."""

    async def latest_business_date(self) -> date | None:
        """Return the latest governed valuation horizon."""

    async def find_open_position_keys(
        self,
        *,
        pair: DirectCurrencyPair,
        effective_date: date,
    ) -> Sequence[PositionValuationKey]:
        """Return open position epochs using exactly the corrected direct pair."""

    async def stage_durable_replay(
        self,
        *,
        correction: FxRateCorrection,
        correlation_id: str,
    ) -> None:
        """Coalesce durable pair/date replay intent."""


class PositionValuationJobWriter(Protocol):
    """Persist idempotent position valuation jobs."""

    async def upsert_job(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        valuation_date: date,
        epoch: int,
        correlation_id: str,
    ) -> object:
        """Stage one position valuation job."""
