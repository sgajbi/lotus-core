from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..dtos.reference_integration_dto import (
    ClientIncomeNeedsScheduleRequest,
    ClientIncomeNeedsScheduleResponse,
    ClientTaxProfileRequest,
    ClientTaxProfileResponse,
    ClientTaxRuleSetRequest,
    ClientTaxRuleSetResponse,
    LiquidityReserveRequirementRequest,
    LiquidityReserveRequirementResponse,
    PlannedWithdrawalScheduleRequest,
    PlannedWithdrawalScheduleResponse,
)
from .client_income_needs_schedule import resolve_client_income_needs_schedule_response
from .client_tax_profile import resolve_client_tax_profile_response
from .client_tax_rule_set import resolve_client_tax_rule_set_response
from .liquidity_reserve_requirement import (
    resolve_liquidity_reserve_requirement_response,
)
from .planned_withdrawal_schedule import resolve_planned_withdrawal_schedule_response


@dataclass(frozen=True)
class ClientProfileIncomeIntegrationService:
    """Contract-family service for client profile, suitability, tax, and income products."""

    reference_repository_provider: Callable[[], Any]

    async def get_client_tax_profile(
        self,
        portfolio_id: str,
        request: ClientTaxProfileRequest,
    ) -> ClientTaxProfileResponse | None:
        return await resolve_client_tax_profile_response(
            repository=self.reference_repository_provider(),
            portfolio_id=portfolio_id,
            request=request,
        )

    async def get_client_tax_rule_set(
        self,
        portfolio_id: str,
        request: ClientTaxRuleSetRequest,
    ) -> ClientTaxRuleSetResponse | None:
        return await resolve_client_tax_rule_set_response(
            repository=self.reference_repository_provider(),
            portfolio_id=portfolio_id,
            request=request,
        )

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
