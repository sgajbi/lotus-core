"""Source-read boundary for client liquidity-planning evidence."""

from datetime import date
from typing import Protocol

from ..domain.client_liquidity_evidence import (
    ClientIncomeNeedSourceRecord,
    LiquidityReserveRequirementSourceRecord,
    PlannedWithdrawalSourceRecord,
)


class ClientLiquidityEvidenceReader(Protocol):
    """Read liquidity-planning evidence without exposing persistence models."""

    async def list_income_needs(
        self,
        *,
        portfolio_id: str,
        client_id: str,
        as_of_date: date,
        mandate_id: str | None,
        include_inactive_schedules: bool,
    ) -> list[ClientIncomeNeedSourceRecord]: ...

    async def list_reserve_requirements(
        self,
        *,
        portfolio_id: str,
        client_id: str,
        as_of_date: date,
        mandate_id: str | None,
        include_inactive_requirements: bool,
    ) -> list[LiquidityReserveRequirementSourceRecord]: ...

    async def list_planned_withdrawals(
        self,
        *,
        portfolio_id: str,
        client_id: str,
        as_of_date: date,
        horizon_days: int,
        mandate_id: str | None,
        include_inactive_withdrawals: bool,
    ) -> list[PlannedWithdrawalSourceRecord]: ...
