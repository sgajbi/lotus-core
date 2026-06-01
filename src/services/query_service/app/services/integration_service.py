import logging
from datetime import UTC, date, datetime
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.integration_dto import EffectiveIntegrationPolicyResponse
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
    ClientIncomeNeedsScheduleRequest,
    ClientIncomeNeedsScheduleResponse,
    ClientRestrictionProfileRequest,
    ClientRestrictionProfileResponse,
    ClientTaxProfileRequest,
    ClientTaxProfileResponse,
    ClientTaxRuleSetRequest,
    ClientTaxRuleSetResponse,
    CoverageResponse,
    DiscretionaryMandateBindingRequest,
    DiscretionaryMandateBindingResponse,
    DpmPortfolioUniverseCandidateRequest,
    DpmPortfolioUniverseCandidateResponse,
    DpmSourceReadinessRequest,
    DpmSourceReadinessResponse,
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
    IndexCatalogResponse,
    IndexPriceSeriesResponse,
    IndexReturnSeriesResponse,
    IndexSeriesRequest,
    InstrumentEligibilityBulkRequest,
    InstrumentEligibilityBulkResponse,
    LiquidityReserveRequirementRequest,
    LiquidityReserveRequirementResponse,
    MarketDataCoverageRequest,
    MarketDataCoverageWindowResponse,
    ModelPortfolioTargetRequest,
    ModelPortfolioTargetResponse,
    PlannedWithdrawalScheduleRequest,
    PlannedWithdrawalScheduleResponse,
    PortfolioManagerBookMembershipRequest,
    PortfolioManagerBookMembershipResponse,
    PortfolioTaxLotWindowRequest,
    PortfolioTaxLotWindowResponse,
    RiskFreeSeriesRequest,
    RiskFreeSeriesResponse,
    SustainabilityPreferenceProfileRequest,
    SustainabilityPreferenceProfileResponse,
    TransactionCostCurveRequest,
    TransactionCostCurveResponse,
)
from ..repositories.buy_state_repository import BuyStateRepository
from ..repositories.currency_codes import normalize_currency_code
from ..repositories.portfolio_repository import PortfolioRepository
from ..repositories.reference_data_repository import ReferenceDataRepository
from ..repositories.transaction_repository import TransactionRepository
from ..settings import load_query_service_settings
from .benchmark_assignment import build_benchmark_assignment_response
from .benchmark_catalog import resolve_benchmark_catalog_response
from .benchmark_composition import (
    resolve_benchmark_composition_window_response,
)
from .benchmark_coverage import build_benchmark_coverage_response
from .benchmark_market_series import (
    resolve_benchmark_market_series_response,
)
from .benchmark_return_series import build_benchmark_return_series_response
from .cio_model_change_cohort import resolve_cio_model_change_affected_cohort_response
from .classification_taxonomy import build_classification_taxonomy_response
from .client_income_needs_schedule import resolve_client_income_needs_schedule_response
from .client_restriction_profile import resolve_client_restriction_profile_response
from .client_tax_profile import resolve_client_tax_profile_response
from .client_tax_rule_set import resolve_client_tax_rule_set_response
from .discretionary_mandate_binding import build_discretionary_mandate_binding_response
from .dpm_portfolio_universe import (
    resolve_dpm_portfolio_universe_candidate_response,
)
from .dpm_source_readiness import (
    DpmSourceReadinessReaders,
    resolve_dpm_source_readiness_response,
)
from .external_currency_exposure import build_external_currency_exposure_response
from .external_eligible_hedge_instrument import (
    build_external_eligible_hedge_instrument_response,
)
from .external_fx_forward_curve import build_external_fx_forward_curve_response
from .external_hedge_execution_readiness import (
    build_external_hedge_execution_readiness_response,
)
from .external_hedge_policy import build_external_hedge_policy_response
from .external_order_execution_acknowledgement import (
    build_external_order_execution_acknowledgement_response,
)
from .index_catalog import build_index_catalog_response
from .index_price_series import build_index_price_series_response
from .index_return_series import build_index_return_series_response
from .instrument_eligibility import build_instrument_eligibility_bulk_response
from .integration_policy import build_effective_policy_response
from .liquidity_reserve_requirement import (
    resolve_liquidity_reserve_requirement_response,
)
from .market_data_coverage import (
    build_market_data_coverage_response,
    market_data_coverage_read_scope,
)
from .model_portfolio_targets import resolve_model_portfolio_target_response
from .page_token_codec import PageTokenCodec
from .planned_withdrawal_schedule import resolve_planned_withdrawal_schedule_response
from .portfolio_manager_book_membership import (
    build_portfolio_manager_book_membership_response,
    portfolio_manager_book_membership_portfolio_types,
)
from .portfolio_tax_lot_window import (
    resolve_portfolio_tax_lot_window_response,
)
from .reference_data_mappers import benchmark_definition_response
from .risk_free_coverage import build_risk_free_coverage_response
from .risk_free_series import build_risk_free_series_response
from .sustainability_preference_profile import (
    resolve_sustainability_preference_profile_response,
)
from .transaction_cost_curve import (
    resolve_transaction_cost_curve_response,
)

logger = logging.getLogger(__name__)


class IntegrationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._reference_repository = ReferenceDataRepository(db)
        self._buy_state_repository = BuyStateRepository(db)
        self._portfolio_repository = PortfolioRepository(db)
        self._transaction_repository = TransactionRepository(db)
        self._page_token_codec = PageTokenCodec(load_query_service_settings().page_token_secret)

    def _encode_page_token(self, payload: dict[str, Any]) -> str:
        return cast(str, self._page_token_codec.encode(payload))

    def _decode_page_token(self, token: str | None) -> dict[str, Any]:
        return cast(dict[str, Any], self._page_token_codec.decode(token))

    def get_effective_policy(
        self,
        consumer_system: str,
        tenant_id: str,
        include_sections: list[str] | None,
    ) -> EffectiveIntegrationPolicyResponse:
        return build_effective_policy_response(
            consumer_system=consumer_system,
            tenant_id=tenant_id,
            include_sections=include_sections,
            generated_at=datetime.now(UTC),
        )

    async def resolve_benchmark_assignment(
        self, portfolio_id: str, as_of_date: date
    ) -> BenchmarkAssignmentResponse | None:
        row = await self._reference_repository.resolve_benchmark_assignment(
            portfolio_id,
            as_of_date,
        )
        if row is None:
            return None
        return build_benchmark_assignment_response(row=row, as_of_date=as_of_date)

    async def resolve_model_portfolio_targets(
        self,
        model_portfolio_id: str,
        request: ModelPortfolioTargetRequest,
    ) -> ModelPortfolioTargetResponse | None:
        return await resolve_model_portfolio_target_response(
            repository=self._reference_repository,
            model_portfolio_id=model_portfolio_id,
            request=request,
        )

    async def resolve_portfolio_manager_book_membership(
        self,
        portfolio_manager_id: str,
        request: PortfolioManagerBookMembershipRequest,
    ) -> PortfolioManagerBookMembershipResponse:
        portfolio_types = portfolio_manager_book_membership_portfolio_types(request)
        rows = await self._portfolio_repository.list_portfolio_manager_book_members(
            portfolio_manager_id=portfolio_manager_id,
            as_of_date=request.as_of_date,
            booking_center_code=request.booking_center_code,
            portfolio_types=portfolio_types,
            include_inactive=request.include_inactive,
        )
        return build_portfolio_manager_book_membership_response(
            portfolio_manager_id=portfolio_manager_id,
            request=request,
            portfolio_types=portfolio_types,
            rows=rows,
        )

    async def resolve_cio_model_change_affected_cohort(
        self,
        model_portfolio_id: str,
        request: CioModelChangeAffectedCohortRequest,
    ) -> CioModelChangeAffectedCohortResponse | None:
        return await resolve_cio_model_change_affected_cohort_response(
            repository=self._reference_repository,
            model_portfolio_id=model_portfolio_id,
            request=request,
        )

    async def resolve_dpm_portfolio_universe_candidates(
        self,
        request: DpmPortfolioUniverseCandidateRequest,
    ) -> DpmPortfolioUniverseCandidateResponse:
        return await resolve_dpm_portfolio_universe_candidate_response(
            repository=self._reference_repository,
            request=request,
            decode_page_token=self._decode_page_token,
            encode_page_token=self._encode_page_token,
        )

    async def resolve_discretionary_mandate_binding(
        self,
        portfolio_id: str,
        request: DiscretionaryMandateBindingRequest,
    ) -> DiscretionaryMandateBindingResponse | None:
        row = await self._reference_repository.resolve_discretionary_mandate_binding(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            mandate_id=request.mandate_id,
            booking_center_code=request.booking_center_code,
        )
        if row is None:
            return None

        return build_discretionary_mandate_binding_response(
            row=row,
            request=request,
        )

    async def get_client_restriction_profile(
        self,
        portfolio_id: str,
        request: ClientRestrictionProfileRequest,
    ) -> ClientRestrictionProfileResponse | None:
        return await resolve_client_restriction_profile_response(
            repository=self._reference_repository,
            portfolio_id=portfolio_id,
            request=request,
        )

    async def get_sustainability_preference_profile(
        self,
        portfolio_id: str,
        request: SustainabilityPreferenceProfileRequest,
    ) -> SustainabilityPreferenceProfileResponse | None:
        return await resolve_sustainability_preference_profile_response(
            repository=self._reference_repository,
            portfolio_id=portfolio_id,
            request=request,
        )

    async def get_client_tax_profile(
        self,
        portfolio_id: str,
        request: ClientTaxProfileRequest,
    ) -> ClientTaxProfileResponse | None:
        return await resolve_client_tax_profile_response(
            repository=self._reference_repository,
            portfolio_id=portfolio_id,
            request=request,
        )

    async def get_client_tax_rule_set(
        self,
        portfolio_id: str,
        request: ClientTaxRuleSetRequest,
    ) -> ClientTaxRuleSetResponse | None:
        return await resolve_client_tax_rule_set_response(
            repository=self._reference_repository,
            portfolio_id=portfolio_id,
            request=request,
        )

    async def get_client_income_needs_schedule(
        self,
        portfolio_id: str,
        request: ClientIncomeNeedsScheduleRequest,
    ) -> ClientIncomeNeedsScheduleResponse | None:
        return await resolve_client_income_needs_schedule_response(
            repository=self._reference_repository,
            portfolio_id=portfolio_id,
            request=request,
        )

    async def get_liquidity_reserve_requirement(
        self,
        portfolio_id: str,
        request: LiquidityReserveRequirementRequest,
    ) -> LiquidityReserveRequirementResponse | None:
        return await resolve_liquidity_reserve_requirement_response(
            repository=self._reference_repository,
            portfolio_id=portfolio_id,
            request=request,
        )

    async def get_planned_withdrawal_schedule(
        self,
        portfolio_id: str,
        request: PlannedWithdrawalScheduleRequest,
    ) -> PlannedWithdrawalScheduleResponse | None:
        return await resolve_planned_withdrawal_schedule_response(
            repository=self._reference_repository,
            portfolio_id=portfolio_id,
            request=request,
        )

    async def get_external_hedge_execution_readiness(
        self,
        portfolio_id: str,
        request: ExternalHedgeExecutionReadinessRequest,
    ) -> ExternalHedgeExecutionReadinessResponse | None:
        binding = await self._reference_repository.resolve_discretionary_mandate_binding(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            mandate_id=request.mandate_id,
        )
        if binding is None:
            return None

        return build_external_hedge_execution_readiness_response(
            portfolio_id=portfolio_id,
            binding=binding,
            request=request,
        )

    async def get_external_currency_exposure(
        self,
        portfolio_id: str,
        request: ExternalCurrencyExposureRequest,
    ) -> ExternalCurrencyExposureResponse | None:
        binding = await self._reference_repository.resolve_discretionary_mandate_binding(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            mandate_id=request.mandate_id,
        )
        if binding is None:
            return None

        return build_external_currency_exposure_response(
            portfolio_id=portfolio_id,
            binding=binding,
            request=request,
        )

    async def get_external_order_execution_acknowledgement(
        self,
        portfolio_id: str,
        request: ExternalOrderExecutionAcknowledgementRequest,
    ) -> ExternalOrderExecutionAcknowledgementResponse | None:
        binding = await self._reference_repository.resolve_discretionary_mandate_binding(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            mandate_id=request.mandate_id,
        )
        if binding is None:
            return None

        return build_external_order_execution_acknowledgement_response(
            portfolio_id=portfolio_id,
            binding=binding,
            request=request,
        )

    async def get_external_hedge_policy(
        self,
        portfolio_id: str,
        request: ExternalHedgePolicyRequest,
    ) -> ExternalHedgePolicyResponse | None:
        binding = await self._reference_repository.resolve_discretionary_mandate_binding(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            mandate_id=request.mandate_id,
        )
        if binding is None:
            return None

        return build_external_hedge_policy_response(
            portfolio_id=portfolio_id,
            binding=binding,
            request=request,
        )

    async def get_external_eligible_hedge_instruments(
        self,
        portfolio_id: str,
        request: ExternalEligibleHedgeInstrumentRequest,
    ) -> ExternalEligibleHedgeInstrumentResponse | None:
        binding = await self._reference_repository.resolve_discretionary_mandate_binding(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            mandate_id=request.mandate_id,
        )
        if binding is None:
            return None

        return build_external_eligible_hedge_instrument_response(
            portfolio_id=portfolio_id,
            binding=binding,
            request=request,
        )

    async def get_external_fx_forward_curve(
        self,
        request: ExternalFXForwardCurveRequest,
    ) -> ExternalFXForwardCurveResponse:
        return build_external_fx_forward_curve_response(request=request)

    async def resolve_instrument_eligibility_bulk(
        self,
        request: InstrumentEligibilityBulkRequest,
    ) -> InstrumentEligibilityBulkResponse:
        rows = await self._reference_repository.list_instrument_eligibility_profiles(
            security_ids=request.security_ids,
            as_of_date=request.as_of_date,
        )
        return build_instrument_eligibility_bulk_response(request=request, rows=rows)

    async def get_portfolio_tax_lot_window(
        self,
        *,
        portfolio_id: str,
        request: PortfolioTaxLotWindowRequest,
    ) -> PortfolioTaxLotWindowResponse:
        return await resolve_portfolio_tax_lot_window_response(
            repository=self._buy_state_repository,
            portfolio_id=portfolio_id,
            request=request,
            decode_page_token=self._decode_page_token,
            encode_page_token=self._encode_page_token,
        )

    async def get_transaction_cost_curve(
        self,
        *,
        portfolio_id: str,
        request: TransactionCostCurveRequest,
    ) -> TransactionCostCurveResponse:
        return await resolve_transaction_cost_curve_response(
            repository=self._transaction_repository,
            portfolio_id=portfolio_id,
            request=request,
            decode_page_token=self._decode_page_token,
            encode_page_token=self._encode_page_token,
        )

    async def get_market_data_coverage(
        self,
        request: MarketDataCoverageRequest,
    ) -> MarketDataCoverageWindowResponse:
        read_scope = market_data_coverage_read_scope(request)
        price_rows = await self._reference_repository.list_latest_market_prices(
            security_ids=read_scope.unique_instrument_ids,
            as_of_date=request.as_of_date,
        )
        fx_rows = await self._reference_repository.list_latest_fx_rates(
            currency_pairs=read_scope.unique_fx_pairs,
            as_of_date=request.as_of_date,
        )
        return build_market_data_coverage_response(
            request=request,
            read_scope=read_scope,
            price_rows=price_rows,
            fx_rows=fx_rows,
        )

    async def get_dpm_source_readiness(
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
                read_tax_lots=lambda scoped_portfolio_id, scoped_request: (
                    self.get_portfolio_tax_lot_window(
                        portfolio_id=scoped_portfolio_id,
                        request=scoped_request,
                    )
                ),
                read_market_data=self.get_market_data_coverage,
            ),
        )

    async def get_benchmark_definition(
        self, benchmark_id: str, as_of_date: date
    ) -> BenchmarkDefinitionResponse | None:
        row = await self._reference_repository.get_benchmark_definition(benchmark_id, as_of_date)
        if row is None:
            return None
        components = await self._reference_repository.list_benchmark_components(
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
            repository=self._reference_repository,
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
            repository=self._reference_repository,
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
        rows = await self._reference_repository.list_index_definitions(
            as_of_date=as_of_date,
            index_ids=index_ids,
            index_currency=index_currency,
            index_type=index_type,
            index_status=index_status,
        )
        return build_index_catalog_response(
            as_of_date=as_of_date,
            rows=rows,
        )

    async def get_benchmark_market_series(
        self,
        benchmark_id: str,
        request: BenchmarkMarketSeriesRequest,
    ) -> BenchmarkMarketSeriesResponse:
        return await resolve_benchmark_market_series_response(
            repository=self._reference_repository,
            benchmark_id=benchmark_id,
            request=request,
            decode_page_token=self._decode_page_token,
            encode_page_token=self._encode_page_token,
        )

    async def get_index_price_series(
        self, index_id: str, request: IndexSeriesRequest
    ) -> IndexPriceSeriesResponse:
        rows = await self._reference_repository.list_index_price_series(
            index_id=index_id,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        )
        return build_index_price_series_response(
            index_id=index_id,
            request=request,
            rows=rows,
        )

    async def get_index_return_series(
        self, index_id: str, request: IndexSeriesRequest
    ) -> IndexReturnSeriesResponse:
        rows = await self._reference_repository.list_index_return_series(
            index_id=index_id,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        )
        return build_index_return_series_response(
            index_id=index_id,
            request=request,
            rows=rows,
        )

    async def get_benchmark_return_series(
        self, benchmark_id: str, request: BenchmarkReturnSeriesRequest
    ) -> BenchmarkReturnSeriesResponse:
        rows = await self._reference_repository.list_benchmark_return_points(
            benchmark_id=benchmark_id,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        )
        return build_benchmark_return_series_response(
            benchmark_id=benchmark_id,
            request=request,
            rows=rows,
        )

    async def get_risk_free_series(self, request: RiskFreeSeriesRequest) -> RiskFreeSeriesResponse:
        normalized_currency = normalize_currency_code(request.currency)
        rows = await self._reference_repository.list_risk_free_series(
            currency=normalized_currency,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        )
        return build_risk_free_series_response(
            currency=normalized_currency,
            request=request,
            rows=rows,
        )

    async def get_benchmark_coverage(
        self,
        benchmark_id: str,
        start_date: date,
        end_date: date,
    ) -> CoverageResponse:
        coverage = await self._reference_repository.get_benchmark_coverage(
            benchmark_id=benchmark_id,
            start_date=start_date,
            end_date=end_date,
        )
        return build_benchmark_coverage_response(
            benchmark_id=benchmark_id,
            coverage=coverage,
            start_date=start_date,
            end_date=end_date,
        )

    async def get_risk_free_coverage(
        self,
        currency: str,
        start_date: date,
        end_date: date,
    ) -> CoverageResponse:
        normalized_currency = normalize_currency_code(currency)
        coverage = await self._reference_repository.get_risk_free_coverage(
            currency=normalized_currency,
            start_date=start_date,
            end_date=end_date,
        )
        return build_risk_free_coverage_response(
            currency=normalized_currency,
            coverage=coverage,
            start_date=start_date,
            end_date=end_date,
        )

    async def get_classification_taxonomy(
        self,
        as_of_date: date,
        taxonomy_scope: str | None = None,
    ) -> ClassificationTaxonomyResponse:
        rows = await self._reference_repository.list_taxonomy(
            as_of_date=as_of_date,
            taxonomy_scope=taxonomy_scope,
        )
        return build_classification_taxonomy_response(
            as_of_date=as_of_date,
            taxonomy_scope=taxonomy_scope,
            rows=rows,
        )
