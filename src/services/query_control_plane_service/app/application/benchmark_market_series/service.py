"""Application use case for governed benchmark component market-series windows."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from ...contracts.benchmark_market_series import (
    BenchmarkMarketSeriesRequest,
    BenchmarkMarketSeriesResponse,
)
from ...domain.benchmark_definition import BenchmarkComponentEvidence
from ...domain.benchmark_return_series import BenchmarkReturnEvidence
from ...domain.index_series import IndexPriceEvidence, IndexReturnEvidence
from ...domain.market_fx import FxRateEvidence
from ...ports.benchmark_definition import BenchmarkDefinitionReader
from ...ports.benchmark_return_series import BenchmarkReturnSeriesReader
from ...ports.index_series import IndexSeriesReader
from ...ports.market_fx import MarketFxRateReader
from ...ports.page_tokens import PageTokenCodecPort
from .assembly import build_benchmark_market_series_response
from .policy import (
    BenchmarkMarketSeriesEvidencePlan,
    build_evidence_plan,
    next_page_token_payload,
    resolve_fx_context,
    resolve_request_scope,
    select_index_page,
)


@dataclass(frozen=True, slots=True)
class BenchmarkMarketSeriesEvidence:
    """Typed source evidence collected for one component page."""

    components: list[BenchmarkComponentEvidence] = field(default_factory=list)
    index_prices: list[IndexPriceEvidence] = field(default_factory=list)
    index_returns: list[IndexReturnEvidence] = field(default_factory=list)
    benchmark_returns: list[BenchmarkReturnEvidence] = field(default_factory=list)
    fx_rates: list[FxRateEvidence] = field(default_factory=list)


class BenchmarkMarketSeriesService:
    """Coordinate typed source reads and build one deterministic market window page."""

    def __init__(
        self,
        *,
        benchmark_reader: BenchmarkDefinitionReader,
        index_series_reader: IndexSeriesReader,
        benchmark_return_reader: BenchmarkReturnSeriesReader,
        fx_rate_reader: MarketFxRateReader,
        page_tokens: PageTokenCodecPort,
        clock: Callable[[], datetime],
    ) -> None:
        self._benchmark_reader = benchmark_reader
        self._index_series_reader = index_series_reader
        self._benchmark_return_reader = benchmark_return_reader
        self._fx_rate_reader = fx_rate_reader
        self._page_tokens = page_tokens
        self._clock = clock

    async def get(
        self, *, benchmark_id: str, request: BenchmarkMarketSeriesRequest
    ) -> BenchmarkMarketSeriesResponse:
        """Resolve source evidence after validating continuation scope."""

        scope = resolve_request_scope(
            benchmark_id=benchmark_id,
            request=request,
            cursor=self._page_tokens.decode(request.page.page_token),
        )
        definition = await self._benchmark_reader.resolve_definition(
            benchmark_id=benchmark_id,
            as_of_date=request.as_of_date,
        )
        candidate_index_ids = await self._benchmark_reader.list_component_index_ids_page(
            benchmark_id=benchmark_id,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
            after_index_id=scope.cursor_index_id,
            limit=scope.page_size + 1,
        )
        index_page = select_index_page(
            candidate_index_ids=candidate_index_ids,
            page_size=scope.page_size,
        )
        benchmark_currency = (
            definition.benchmark_currency
            if definition is not None
            else request.target_currency or "UNKNOWN"
        )
        fx_context = resolve_fx_context(
            benchmark_currency=benchmark_currency,
            target_currency=request.target_currency,
            requested_fields=scope.requested_fields,
        )
        evidence_plan = build_evidence_plan(
            requested_fields=scope.requested_fields,
            fx_context=fx_context,
        )
        evidence = await self._read_evidence(
            benchmark_id=benchmark_id,
            request=request,
            index_ids=index_page.index_ids,
            evidence_plan=evidence_plan,
            benchmark_currency=benchmark_currency,
        )
        token_payload = next_page_token_payload(
            request_scope=scope,
            index_page=index_page,
        )
        next_token = self._page_tokens.encode(token_payload) if token_payload else None
        return build_benchmark_market_series_response(
            benchmark_id=benchmark_id,
            request=request,
            definition=definition,
            request_fingerprint=scope.request_fingerprint,
            page_size=scope.page_size,
            has_more=index_page.has_more,
            next_page_token=next_token,
            index_ids=index_page.index_ids,
            components=evidence.components,
            index_prices=evidence.index_prices,
            index_returns=evidence.index_returns,
            benchmark_returns=evidence.benchmark_returns,
            fx_rates=evidence.fx_rates,
            fx_context=fx_context,
            generated_at=self._clock(),
        )

    async def _read_evidence(
        self,
        *,
        benchmark_id: str,
        request: BenchmarkMarketSeriesRequest,
        index_ids: tuple[str, ...],
        evidence_plan: BenchmarkMarketSeriesEvidencePlan,
        benchmark_currency: str,
    ) -> BenchmarkMarketSeriesEvidence:
        if not index_ids:
            return BenchmarkMarketSeriesEvidence()
        requested_index_ids = list(index_ids)
        components = await self._benchmark_reader.list_components_for_indices_overlapping_window(
            benchmark_id=benchmark_id,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
            index_ids=requested_index_ids,
        )
        index_prices: list[IndexPriceEvidence] = []
        if evidence_plan.include_index_prices:
            index_prices = await self._index_series_reader.list_prices_for_indices(
                index_ids=requested_index_ids,
                start_date=request.window.start_date,
                end_date=request.window.end_date,
            )
        index_returns: list[IndexReturnEvidence] = []
        if evidence_plan.include_index_returns:
            index_returns = await self._index_series_reader.list_returns_for_indices(
                index_ids=requested_index_ids,
                start_date=request.window.start_date,
                end_date=request.window.end_date,
            )
        benchmark_returns: list[BenchmarkReturnEvidence] = []
        if evidence_plan.include_benchmark_returns:
            benchmark_returns = await self._benchmark_return_reader.list_returns(
                benchmark_id=benchmark_id,
                start_date=request.window.start_date,
                end_date=request.window.end_date,
            )
        fx_rates: list[FxRateEvidence] = []
        if evidence_plan.include_fx_rates and request.target_currency is not None:
            fx_rates = await self._fx_rate_reader.list_rates(
                from_currency=benchmark_currency,
                to_currency=request.target_currency,
                start_date=request.window.start_date,
                end_date=request.window.end_date,
            )
        return BenchmarkMarketSeriesEvidence(
            components=components,
            index_prices=index_prices,
            index_returns=index_returns,
            benchmark_returns=benchmark_returns,
            fx_rates=fx_rates,
        )
