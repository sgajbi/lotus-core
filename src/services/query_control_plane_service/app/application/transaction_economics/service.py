"""Application service for transaction-cost and performance-economics products."""

from portfolio_common.runtime_providers import Clock

from ...contracts.performance_component_economics import (
    PerformanceComponentEconomicsRequest,
    PerformanceComponentEconomicsResponse,
)
from ...contracts.transaction_cost_curve import (
    TransactionCostCurveRequest,
    TransactionCostCurveResponse,
)
from ...ports.transaction_economics import (
    TransactionEconomicsPageTokenCodec,
    TransactionEconomicsReader,
)
from .cost_curve import resolve_transaction_cost_curve_response
from .performance import resolve_performance_component_economics_response


class TransactionEconomicsService:
    """Resolve QCP-owned economics evidence through explicit ports."""

    def __init__(
        self,
        *,
        reader: TransactionEconomicsReader,
        page_tokens: TransactionEconomicsPageTokenCodec,
        clock: Clock,
    ) -> None:
        self._reader = reader
        self._page_tokens = page_tokens
        self._clock = clock

    async def get_transaction_cost_curve(
        self,
        *,
        portfolio_id: str,
        request: TransactionCostCurveRequest,
    ) -> TransactionCostCurveResponse:
        return await resolve_transaction_cost_curve_response(
            repository=self._reader,
            portfolio_id=portfolio_id,
            request=request,
            decode_page_token=self._page_tokens.decode,
            encode_page_token=self._page_tokens.encode,
            generated_at=self._clock.utc_now(),
        )

    async def get_performance_component_economics(
        self,
        *,
        portfolio_id: str,
        request: PerformanceComponentEconomicsRequest,
    ) -> PerformanceComponentEconomicsResponse:
        return await resolve_performance_component_economics_response(
            repository=self._reader,
            portfolio_id=portfolio_id,
            request=request,
            decode_page_token=self._page_tokens.decode,
            encode_page_token=self._page_tokens.encode,
            generated_at=self._clock.utc_now(),
        )
