import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, cast

from portfolio_common.page_tokens import PageTokenCodec
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.reference_integration_dto import (
    BenchmarkCatalogResponse,
    BenchmarkCompositionWindowRequest,
    BenchmarkCompositionWindowResponse,
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
from ..repositories.reference_data_repository import ReferenceDataRepository
from ..settings import load_query_service_settings
from .benchmark_reference_integration_service import BenchmarkReferenceIntegrationService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IntegrationServiceDependencies:
    reference_repository: ReferenceDataRepository
    page_token_codec: PageTokenCodec

    @classmethod
    def from_session(cls, db: AsyncSession) -> "IntegrationServiceDependencies":
        settings = load_query_service_settings()
        return cls(
            reference_repository=ReferenceDataRepository(db),
            page_token_codec=PageTokenCodec(
                secret=settings.page_token_secret,
                active_kid=settings.page_token_key_id,
                previous_secrets=settings.page_token_previous_keys,
                ttl_seconds=settings.page_token_ttl_seconds,
            ),
        )


class IntegrationService:
    def __init__(
        self,
        db: AsyncSession | None = None,
        *,
        dependencies: IntegrationServiceDependencies | None = None,
    ):
        if dependencies is None:
            if db is None:
                raise ValueError("IntegrationService requires db or dependencies")
            dependencies = IntegrationServiceDependencies.from_session(db)
        self.db = db
        self._reference_repository = dependencies.reference_repository
        self._page_token_codec = dependencies.page_token_codec
        self._benchmark_reference_service = BenchmarkReferenceIntegrationService(
            reference_repository_provider=lambda: self._reference_repository,
            decode_page_token=self._decode_page_token,
            encode_page_token=self._encode_page_token,
        )

    def _encode_page_token(self, payload: dict[str, Any]) -> str:
        return cast(str, self._page_token_codec.encode(payload))

    def _decode_page_token(self, token: str | None) -> dict[str, Any]:
        return cast(dict[str, Any], self._page_token_codec.decode(token))

    async def get_benchmark_composition_window(
        self,
        benchmark_id: str,
        request: BenchmarkCompositionWindowRequest,
    ) -> BenchmarkCompositionWindowResponse | None:
        return await self._benchmark_reference_service.get_benchmark_composition_window(
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
        return await self._benchmark_reference_service.list_benchmark_catalog(
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
        return await self._benchmark_reference_service.list_index_catalog(
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
        return await self._benchmark_reference_service.get_benchmark_market_series(
            benchmark_id=benchmark_id,
            request=request,
        )

    async def get_index_price_series(
        self, index_id: str, request: IndexSeriesRequest
    ) -> IndexPriceSeriesResponse:
        return await self._benchmark_reference_service.get_index_price_series(
            index_id=index_id,
            request=request,
        )

    async def get_index_return_series(
        self, index_id: str, request: IndexSeriesRequest
    ) -> IndexReturnSeriesResponse:
        return await self._benchmark_reference_service.get_index_return_series(
            index_id=index_id,
            request=request,
        )

    async def get_benchmark_return_series(
        self, benchmark_id: str, request: BenchmarkReturnSeriesRequest
    ) -> BenchmarkReturnSeriesResponse:
        return await self._benchmark_reference_service.get_benchmark_return_series(
            benchmark_id=benchmark_id,
            request=request,
        )

    async def get_risk_free_series(self, request: RiskFreeSeriesRequest) -> RiskFreeSeriesResponse:
        return await self._benchmark_reference_service.get_risk_free_series(request)

    async def get_benchmark_coverage(
        self,
        benchmark_id: str,
        start_date: date,
        end_date: date,
    ) -> CoverageResponse:
        return await self._benchmark_reference_service.get_benchmark_coverage(
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
        return await self._benchmark_reference_service.get_risk_free_coverage(
            currency=currency,
            start_date=start_date,
            end_date=end_date,
        )

    async def get_classification_taxonomy(
        self,
        as_of_date: date,
        taxonomy_scope: str | None = None,
    ) -> ClassificationTaxonomyResponse:
        return await self._benchmark_reference_service.get_classification_taxonomy(
            as_of_date=as_of_date,
            taxonomy_scope=taxonomy_scope,
        )
