from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..dtos.reference_integration_dto import (
    ExternalCurrencyExposureRequest,
    ExternalCurrencyExposureResponse,
    ExternalEligibleHedgeInstrumentRequest,
    ExternalEligibleHedgeInstrumentResponse,
    ExternalFXForwardCurveRequest,
    ExternalFXForwardCurveResponse,
    ExternalHedgeExecutionReadinessRequest,
    ExternalHedgeExecutionReadinessResponse,
    ExternalHedgePolicyRequest,
    ExternalHedgePolicyResponse,
    ExternalOrderExecutionAcknowledgementRequest,
    ExternalOrderExecutionAcknowledgementResponse,
)
from .external_currency_exposure import resolve_external_currency_exposure_response
from .external_eligible_hedge_instrument import (
    resolve_external_eligible_hedge_instrument_response,
)
from .external_fx_forward_curve import build_external_fx_forward_curve_response
from .external_hedge_execution_readiness import (
    resolve_external_hedge_execution_readiness_response,
)
from .external_hedge_policy import resolve_external_hedge_policy_response
from .external_order_execution_acknowledgement import (
    resolve_external_order_execution_acknowledgement_response,
)


@dataclass(frozen=True)
class ExternalHedgeIntegrationService:
    """Contract-family service for external hedge and OMS source-data products."""

    reference_repository_provider: Callable[[], Any]

    async def get_execution_readiness(
        self,
        portfolio_id: str,
        request: ExternalHedgeExecutionReadinessRequest,
    ) -> ExternalHedgeExecutionReadinessResponse | None:
        return await resolve_external_hedge_execution_readiness_response(
            repository=self.reference_repository_provider(),
            portfolio_id=portfolio_id,
            request=request,
        )

    async def get_currency_exposure(
        self,
        portfolio_id: str,
        request: ExternalCurrencyExposureRequest,
    ) -> ExternalCurrencyExposureResponse | None:
        return await resolve_external_currency_exposure_response(
            repository=self.reference_repository_provider(),
            portfolio_id=portfolio_id,
            request=request,
        )

    async def get_order_execution_acknowledgement(
        self,
        portfolio_id: str,
        request: ExternalOrderExecutionAcknowledgementRequest,
    ) -> ExternalOrderExecutionAcknowledgementResponse | None:
        return await resolve_external_order_execution_acknowledgement_response(
            repository=self.reference_repository_provider(),
            portfolio_id=portfolio_id,
            request=request,
        )

    async def get_hedge_policy(
        self,
        portfolio_id: str,
        request: ExternalHedgePolicyRequest,
    ) -> ExternalHedgePolicyResponse | None:
        return await resolve_external_hedge_policy_response(
            repository=self.reference_repository_provider(),
            portfolio_id=portfolio_id,
            request=request,
        )

    async def get_eligible_hedge_instruments(
        self,
        portfolio_id: str,
        request: ExternalEligibleHedgeInstrumentRequest,
    ) -> ExternalEligibleHedgeInstrumentResponse | None:
        return await resolve_external_eligible_hedge_instrument_response(
            repository=self.reference_repository_provider(),
            portfolio_id=portfolio_id,
            request=request,
        )

    async def get_fx_forward_curve(
        self,
        request: ExternalFXForwardCurveRequest,
    ) -> ExternalFXForwardCurveResponse:
        return build_external_fx_forward_curve_response(request=request)
