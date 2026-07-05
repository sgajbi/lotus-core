from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..dtos.reference_integration_dto import (
    PerformanceComponentEconomicsRequest,
    PerformanceComponentEconomicsResponse,
    TransactionCostCurveRequest,
    TransactionCostCurveResponse,
)
from .performance_component_economics import (
    resolve_performance_component_economics_response,
)
from .transaction_cost_curve import resolve_transaction_cost_curve_response


@dataclass(frozen=True)
class TransactionEconomicsIntegrationService:
    """Contract-family service for transaction cost and performance economics products."""

    transaction_repository_provider: Callable[[], Any]
    decode_page_token: Callable[[str | None], dict[str, Any]]
    encode_page_token: Callable[[dict[str, Any]], str]

    async def get_transaction_cost_curve(
        self,
        *,
        portfolio_id: str,
        request: TransactionCostCurveRequest,
    ) -> TransactionCostCurveResponse:
        return await resolve_transaction_cost_curve_response(
            repository=self.transaction_repository_provider(),
            portfolio_id=portfolio_id,
            request=request,
            decode_page_token=self.decode_page_token,
            encode_page_token=self.encode_page_token,
        )

    async def get_performance_component_economics(
        self,
        *,
        portfolio_id: str,
        request: PerformanceComponentEconomicsRequest,
    ) -> PerformanceComponentEconomicsResponse:
        return await resolve_performance_component_economics_response(
            repository=self.transaction_repository_provider(),
            portfolio_id=portfolio_id,
            request=request,
            decode_page_token=self.decode_page_token,
            encode_page_token=self.encode_page_token,
        )
