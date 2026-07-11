import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, cast

from portfolio_common.page_tokens import PageTokenCodec
from sqlalchemy.ext.asyncio import AsyncSession

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
    CioModelChangeAffectedCohortRequest,
    CioModelChangeAffectedCohortResponse,
    ClassificationTaxonomyResponse,
    CoverageResponse,
    DiscretionaryMandateBindingRequest,
    DiscretionaryMandateBindingResponse,
    DpmPortfolioUniverseCandidateRequest,
    DpmPortfolioUniverseCandidateResponse,
    DpmSourceReadinessRequest,
    DpmSourceReadinessResponse,
    IndexCatalogResponse,
    IndexPriceSeriesResponse,
    IndexReturnSeriesResponse,
    IndexSeriesRequest,
    InstrumentEligibilityBulkRequest,
    InstrumentEligibilityBulkResponse,
    MarketDataCoverageRequest,
    MarketDataCoverageWindowResponse,
    ModelPortfolioTargetRequest,
    ModelPortfolioTargetResponse,
    PerformanceComponentEconomicsRequest,
    PerformanceComponentEconomicsResponse,
    PortfolioManagerBookMembershipRequest,
    PortfolioManagerBookMembershipResponse,
    PortfolioTaxLotWindowRequest,
    PortfolioTaxLotWindowResponse,
    RiskFreeSeriesRequest,
    RiskFreeSeriesResponse,
    TransactionCostCurveRequest,
    TransactionCostCurveResponse,
)
from ..repositories.buy_state_repository import BuyStateRepository
from ..repositories.portfolio_repository import PortfolioRepository
from ..repositories.reference_data_repository import ReferenceDataRepository
from ..repositories.transaction_repository import TransactionRepository
from ..settings import load_query_service_settings
from .benchmark_reference_integration_service import BenchmarkReferenceIntegrationService
from .dpm_portfolio_management_integration_service import (
    DpmPortfolioManagementIntegrationService,
)
from .dpm_readiness_integration_service import DpmReadinessIntegrationService
from .transaction_economics_integration_service import TransactionEconomicsIntegrationService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IntegrationServiceDependencies:
    reference_repository: ReferenceDataRepository
    buy_state_repository: BuyStateRepository
    portfolio_repository: PortfolioRepository
    transaction_repository: TransactionRepository
    page_token_codec: PageTokenCodec

    @classmethod
    def from_session(cls, db: AsyncSession) -> "IntegrationServiceDependencies":
        settings = load_query_service_settings()
        return cls(
            reference_repository=ReferenceDataRepository(db),
            buy_state_repository=BuyStateRepository(db),
            portfolio_repository=PortfolioRepository(db),
            transaction_repository=TransactionRepository(db),
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
        self._buy_state_repository = dependencies.buy_state_repository
        self._portfolio_repository = dependencies.portfolio_repository
        self._transaction_repository = dependencies.transaction_repository
        self._page_token_codec = dependencies.page_token_codec
        self._dpm_readiness_service = DpmReadinessIntegrationService.from_facade(
            reference_repository_provider=lambda: self._reference_repository,
            buy_state_repository_provider=lambda: self._buy_state_repository,
            decode_page_token=self._decode_page_token,
            encode_page_token=self._encode_page_token,
        )
        self._transaction_economics_service = TransactionEconomicsIntegrationService(
            transaction_repository_provider=lambda: self._transaction_repository,
            decode_page_token=self._decode_page_token,
            encode_page_token=self._encode_page_token,
        )
        self._benchmark_reference_service = BenchmarkReferenceIntegrationService(
            reference_repository_provider=lambda: self._reference_repository,
            decode_page_token=self._decode_page_token,
            encode_page_token=self._encode_page_token,
        )
        self._dpm_portfolio_management_service = DpmPortfolioManagementIntegrationService(
            reference_repository_provider=lambda: self._reference_repository,
            portfolio_repository_provider=lambda: self._portfolio_repository,
            decode_page_token=self._decode_page_token,
            encode_page_token=self._encode_page_token,
        )

    def _encode_page_token(self, payload: dict[str, Any]) -> str:
        return cast(str, self._page_token_codec.encode(payload))

    def _decode_page_token(self, token: str | None) -> dict[str, Any]:
        return cast(dict[str, Any], self._page_token_codec.decode(token))

    async def resolve_benchmark_assignment(
        self, portfolio_id: str, as_of_date: date
    ) -> BenchmarkAssignmentResponse | None:
        return await self._benchmark_reference_service.resolve_benchmark_assignment(
            portfolio_id=portfolio_id,
            as_of_date=as_of_date,
        )

    async def resolve_model_portfolio_targets(
        self,
        model_portfolio_id: str,
        request: ModelPortfolioTargetRequest,
    ) -> ModelPortfolioTargetResponse | None:
        return await self._dpm_readiness_service.resolve_model_portfolio_targets(
            model_portfolio_id=model_portfolio_id,
            request=request,
        )

    async def resolve_portfolio_manager_book_membership(
        self,
        portfolio_manager_id: str,
        request: PortfolioManagerBookMembershipRequest,
    ) -> PortfolioManagerBookMembershipResponse:
        return (
            await self._dpm_portfolio_management_service.resolve_portfolio_manager_book_membership(
                portfolio_manager_id=portfolio_manager_id,
                request=request,
            )
        )

    async def resolve_cio_model_change_affected_cohort(
        self,
        model_portfolio_id: str,
        request: CioModelChangeAffectedCohortRequest,
    ) -> CioModelChangeAffectedCohortResponse | None:
        return (
            await self._dpm_portfolio_management_service.resolve_cio_model_change_affected_cohort(
                model_portfolio_id=model_portfolio_id,
                request=request,
            )
        )

    async def resolve_dpm_portfolio_universe_candidates(
        self,
        request: DpmPortfolioUniverseCandidateRequest,
    ) -> DpmPortfolioUniverseCandidateResponse:
        return (
            await self._dpm_portfolio_management_service.resolve_dpm_portfolio_universe_candidates(
                request=request,
            )
        )

    async def resolve_discretionary_mandate_binding(
        self,
        portfolio_id: str,
        request: DiscretionaryMandateBindingRequest,
    ) -> DiscretionaryMandateBindingResponse | None:
        return await self._dpm_readiness_service.resolve_discretionary_mandate_binding(
            portfolio_id=portfolio_id,
            request=request,
        )

    async def resolve_instrument_eligibility_bulk(
        self,
        request: InstrumentEligibilityBulkRequest,
    ) -> InstrumentEligibilityBulkResponse:
        return await self._dpm_readiness_service.resolve_instrument_eligibility_bulk(request)

    async def get_portfolio_tax_lot_window(
        self,
        *,
        portfolio_id: str,
        request: PortfolioTaxLotWindowRequest,
    ) -> PortfolioTaxLotWindowResponse:
        return await self._dpm_readiness_service.get_portfolio_tax_lot_window(
            portfolio_id=portfolio_id,
            request=request,
        )

    async def get_transaction_cost_curve(
        self,
        *,
        portfolio_id: str,
        request: TransactionCostCurveRequest,
    ) -> TransactionCostCurveResponse:
        return await self._transaction_economics_service.get_transaction_cost_curve(
            portfolio_id=portfolio_id,
            request=request,
        )

    async def get_performance_component_economics(
        self,
        *,
        portfolio_id: str,
        request: PerformanceComponentEconomicsRequest,
    ) -> PerformanceComponentEconomicsResponse:
        return await self._transaction_economics_service.get_performance_component_economics(
            portfolio_id=portfolio_id,
            request=request,
        )

    async def get_market_data_coverage(
        self,
        request: MarketDataCoverageRequest,
    ) -> MarketDataCoverageWindowResponse:
        return await self._dpm_readiness_service.get_market_data_coverage(request)

    async def get_dpm_source_readiness(
        self,
        *,
        portfolio_id: str,
        request: DpmSourceReadinessRequest,
    ) -> DpmSourceReadinessResponse:
        return await self._dpm_readiness_service.get_source_readiness(
            portfolio_id=portfolio_id,
            request=request,
        )

    async def get_benchmark_definition(
        self, benchmark_id: str, as_of_date: date
    ) -> BenchmarkDefinitionResponse | None:
        return await self._benchmark_reference_service.get_benchmark_definition(
            benchmark_id=benchmark_id,
            as_of_date=as_of_date,
        )

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
