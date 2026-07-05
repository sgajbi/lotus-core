from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from ..dtos.reference_integration_dto import (
    BenchmarkAssignmentResponse,
    BenchmarkCatalogResponse,
    BenchmarkCompositionWindowRequest,
    BenchmarkCompositionWindowResponse,
    BenchmarkDefinitionResponse,
    BenchmarkMarketSeriesRequest,
    BenchmarkMarketSeriesResponse,
    BenchmarkReturnSeriesRequest,
    BenchmarkReturnSeriesResponse,
    ClassificationTaxonomyResponse,
    CoverageResponse,
    IndexCatalogResponse,
    IndexPriceSeriesResponse,
    IndexReturnSeriesResponse,
    IndexSeriesRequest,
    RiskFreeSeriesRequest,
    RiskFreeSeriesResponse,
)
from .benchmark_assignment import build_benchmark_assignment_response
from .benchmark_catalog import resolve_benchmark_catalog_response
from .benchmark_composition import resolve_benchmark_composition_window_response
from .benchmark_coverage import resolve_benchmark_coverage_response
from .benchmark_market_series import resolve_benchmark_market_series_response
from .benchmark_return_series import resolve_benchmark_return_series_response
from .classification_taxonomy import resolve_classification_taxonomy_response
from .index_catalog import resolve_index_catalog_response
from .index_price_series import resolve_index_price_series_response
from .index_return_series import resolve_index_return_series_response
from .reference_data_mappers import benchmark_definition_response
from .risk_free_coverage import resolve_risk_free_coverage_response
from .risk_free_series import resolve_risk_free_series_response


@dataclass(frozen=True)
class BenchmarkReferenceIntegrationService:
    """Contract-family service for benchmark and market reference products."""

    reference_repository_provider: Callable[[], Any]
    decode_page_token: Callable[[str | None], dict[str, Any]]
    encode_page_token: Callable[[dict[str, Any]], str]

    async def resolve_benchmark_assignment(
        self,
        portfolio_id: str,
        as_of_date: date,
    ) -> BenchmarkAssignmentResponse | None:
        row = await self.reference_repository_provider().resolve_benchmark_assignment(
            portfolio_id,
            as_of_date,
        )
        if row is None:
            return None
        return build_benchmark_assignment_response(row=row, as_of_date=as_of_date)

    async def get_benchmark_definition(
        self,
        benchmark_id: str,
        as_of_date: date,
    ) -> BenchmarkDefinitionResponse | None:
        repository = self.reference_repository_provider()
        row = await repository.get_benchmark_definition(benchmark_id, as_of_date)
        if row is None:
            return None
        components = await repository.list_benchmark_components(
            benchmark_id,
            as_of_date,
        )
        return benchmark_definition_response(row, components=components)

    async def get_benchmark_composition_window(
        self,
        benchmark_id: str,
        request: BenchmarkCompositionWindowRequest,
    ) -> BenchmarkCompositionWindowResponse | None:
        return await resolve_benchmark_composition_window_response(
            repository=self.reference_repository_provider(),
            benchmark_id=benchmark_id,
            request=request,
        )

    async def list_benchmark_catalog(
        self,
        as_of_date: date,
        benchmark_type: str | None,
        benchmark_currency: str | None,
        benchmark_status: str | None,
    ) -> BenchmarkCatalogResponse:
        return await resolve_benchmark_catalog_response(
            repository=self.reference_repository_provider(),
            as_of_date=as_of_date,
            benchmark_type=benchmark_type,
            benchmark_currency=benchmark_currency,
            benchmark_status=benchmark_status,
        )

    async def list_index_catalog(
        self,
        as_of_date: date,
        index_ids: list[str],
        index_currency: str | None,
        index_type: str | None,
        index_status: str | None,
    ) -> IndexCatalogResponse:
        return await resolve_index_catalog_response(
            repository=self.reference_repository_provider(),
            as_of_date=as_of_date,
            index_ids=index_ids,
            index_currency=index_currency,
            index_type=index_type,
            index_status=index_status,
        )

    async def get_benchmark_market_series(
        self,
        benchmark_id: str,
        request: BenchmarkMarketSeriesRequest,
    ) -> BenchmarkMarketSeriesResponse:
        return await resolve_benchmark_market_series_response(
            repository=self.reference_repository_provider(),
            benchmark_id=benchmark_id,
            request=request,
            decode_page_token=self.decode_page_token,
            encode_page_token=self.encode_page_token,
        )

    async def get_index_price_series(
        self,
        index_id: str,
        request: IndexSeriesRequest,
    ) -> IndexPriceSeriesResponse:
        return await resolve_index_price_series_response(
            repository=self.reference_repository_provider(),
            index_id=index_id,
            request=request,
        )

    async def get_index_return_series(
        self,
        index_id: str,
        request: IndexSeriesRequest,
    ) -> IndexReturnSeriesResponse:
        return await resolve_index_return_series_response(
            repository=self.reference_repository_provider(),
            index_id=index_id,
            request=request,
        )

    async def get_benchmark_return_series(
        self,
        benchmark_id: str,
        request: BenchmarkReturnSeriesRequest,
    ) -> BenchmarkReturnSeriesResponse:
        return await resolve_benchmark_return_series_response(
            repository=self.reference_repository_provider(),
            benchmark_id=benchmark_id,
            request=request,
        )

    async def get_risk_free_series(
        self,
        request: RiskFreeSeriesRequest,
    ) -> RiskFreeSeriesResponse:
        return await resolve_risk_free_series_response(
            repository=self.reference_repository_provider(),
            request=request,
        )

    async def get_benchmark_coverage(
        self,
        benchmark_id: str,
        start_date: date,
        end_date: date,
    ) -> CoverageResponse:
        return await resolve_benchmark_coverage_response(
            repository=self.reference_repository_provider(),
            benchmark_id=benchmark_id,
            start_date=start_date,
            end_date=end_date,
        )

    async def get_risk_free_coverage(
        self,
        currency: str,
        start_date: date,
        end_date: date,
    ) -> CoverageResponse:
        return await resolve_risk_free_coverage_response(
            repository=self.reference_repository_provider(),
            currency=currency,
            start_date=start_date,
            end_date=end_date,
        )

    async def get_classification_taxonomy(
        self,
        as_of_date: date,
        taxonomy_scope: str | None = None,
    ) -> ClassificationTaxonomyResponse:
        return await resolve_classification_taxonomy_response(
            repository=self.reference_repository_provider(),
            as_of_date=as_of_date,
            taxonomy_scope=taxonomy_scope,
        )
