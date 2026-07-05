from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from ..dtos.reference_integration_dto import (
    DiscretionaryMandateBindingRequest,
    DiscretionaryMandateBindingResponse,
    DpmSourceReadinessRequest,
    DpmSourceReadinessResponse,
    InstrumentEligibilityBulkRequest,
    InstrumentEligibilityBulkResponse,
    MarketDataCoverageRequest,
    MarketDataCoverageWindowResponse,
    ModelPortfolioTargetRequest,
    ModelPortfolioTargetResponse,
    PortfolioTaxLotWindowRequest,
    PortfolioTaxLotWindowResponse,
)
from .discretionary_mandate_binding import resolve_discretionary_mandate_binding_response
from .dpm_source_readiness import (
    DpmSourceReadinessReaders,
    resolve_dpm_source_readiness_response,
)
from .instrument_eligibility import resolve_instrument_eligibility_bulk_response
from .market_data_coverage import resolve_market_data_coverage_response
from .model_portfolio_targets import resolve_model_portfolio_target_response
from .portfolio_tax_lot_window import resolve_portfolio_tax_lot_window_response


@dataclass
class DpmReadinessIntegrationService:
    """Contract-family service for DPM source-readiness integration."""

    reference_repository_provider: Callable[[], Any]
    buy_state_repository_provider: Callable[[], Any]
    decode_page_token: Callable[[str | None], dict[str, Any]]
    encode_page_token: Callable[[dict[str, Any]], str]

    async def resolve_model_portfolio_targets(
        self,
        model_portfolio_id: str,
        request: ModelPortfolioTargetRequest,
    ) -> ModelPortfolioTargetResponse | None:
        return await resolve_model_portfolio_target_response(
            repository=self.reference_repository_provider(),
            model_portfolio_id=model_portfolio_id,
            request=request,
        )

    async def resolve_discretionary_mandate_binding(
        self,
        portfolio_id: str,
        request: DiscretionaryMandateBindingRequest,
    ) -> DiscretionaryMandateBindingResponse | None:
        return await resolve_discretionary_mandate_binding_response(
            repository=self.reference_repository_provider(),
            portfolio_id=portfolio_id,
            request=request,
        )

    async def resolve_instrument_eligibility_bulk(
        self,
        request: InstrumentEligibilityBulkRequest,
    ) -> InstrumentEligibilityBulkResponse:
        return await resolve_instrument_eligibility_bulk_response(
            repository=self.reference_repository_provider(),
            request=request,
        )

    async def get_portfolio_tax_lot_window(
        self,
        *,
        portfolio_id: str,
        request: PortfolioTaxLotWindowRequest,
    ) -> PortfolioTaxLotWindowResponse:
        return await resolve_portfolio_tax_lot_window_response(
            repository=self.buy_state_repository_provider(),
            portfolio_id=portfolio_id,
            request=request,
            decode_page_token=self.decode_page_token,
            encode_page_token=self.encode_page_token,
        )

    async def get_market_data_coverage(
        self,
        request: MarketDataCoverageRequest,
    ) -> MarketDataCoverageWindowResponse:
        return await resolve_market_data_coverage_response(
            repository=self.reference_repository_provider(),
            request=request,
        )

    async def get_source_readiness(
        self,
        *,
        portfolio_id: str,
        request: DpmSourceReadinessRequest,
    ) -> DpmSourceReadinessResponse:
        return await resolve_dpm_source_readiness_response(
            portfolio_id=portfolio_id,
            request=request,
            readers=DpmSourceReadinessReaders(
                read_mandate_binding=self.resolve_discretionary_mandate_binding,
                read_model_targets=self.resolve_model_portfolio_targets,
                read_eligibility=self.resolve_instrument_eligibility_bulk,
                read_tax_lots=self._read_tax_lots,
                read_market_data=self.get_market_data_coverage,
            ),
        )

    async def _read_tax_lots(
        self,
        portfolio_id: str,
        request: PortfolioTaxLotWindowRequest,
    ) -> PortfolioTaxLotWindowResponse:
        return await self.get_portfolio_tax_lot_window(
            portfolio_id=portfolio_id,
            request=request,
        )

    @classmethod
    def from_facade(
        cls,
        *,
        reference_repository_provider: Callable[[], Any],
        buy_state_repository_provider: Callable[[], Any],
        decode_page_token: Callable[[str | None], dict[str, Any]],
        encode_page_token: Callable[[dict[str, Any]], str],
    ) -> "DpmReadinessIntegrationService":
        return cls(
            reference_repository_provider=reference_repository_provider,
            buy_state_repository_provider=buy_state_repository_provider,
            decode_page_token=decode_page_token,
            encode_page_token=lambda payload: cast(str, encode_page_token(payload)),
        )
