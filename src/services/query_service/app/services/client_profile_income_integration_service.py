from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..dtos.reference_integration_dto import (
    ClientIncomeNeedsScheduleRequest,
    ClientIncomeNeedsScheduleResponse,
    LiquidityReserveRequirementRequest,
    LiquidityReserveRequirementResponse,
    PlannedWithdrawalScheduleRequest,
    PlannedWithdrawalScheduleResponse,
)
from .client_income_needs_schedule import resolve_client_income_needs_schedule_response
from .liquidity_reserve_requirement import (
    resolve_liquidity_reserve_requirement_response,
)
from .planned_withdrawal_schedule import resolve_planned_withdrawal_schedule_response


@dataclass(frozen=True)
class ClientProfileIncomeIntegrationService:
    """Contract-family service for client profile, suitability, tax, and income products."""

    reference_repository_provider: Callable[[], Any]

    async def get_client_income_needs_schedule(
        self,
        portfolio_id: str,
        request: ClientIncomeNeedsScheduleRequest,
    ) -> ClientIncomeNeedsScheduleResponse | None:
        return await resolve_client_income_needs_schedule_response(
            repository=self.reference_repository_provider(),
            portfolio_id=portfolio_id,
            request=request,
        )

    async def get_liquidity_reserve_requirement(
        self,
        portfolio_id: str,
        request: LiquidityReserveRequirementRequest,
    ) -> LiquidityReserveRequirementResponse | None:
        return await resolve_liquidity_reserve_requirement_response(
            repository=self.reference_repository_provider(),
            portfolio_id=portfolio_id,
            request=request,
        )

    async def get_planned_withdrawal_schedule(
        self,
        portfolio_id: str,
        request: PlannedWithdrawalScheduleRequest,
    ) -> PlannedWithdrawalScheduleResponse | None:
        return await resolve_planned_withdrawal_schedule_response(
            repository=self.reference_repository_provider(),
            portfolio_id=portfolio_id,
            request=request,
        )
