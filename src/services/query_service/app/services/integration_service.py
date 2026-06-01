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
    DpmSourceFamilyReadiness,
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
from .benchmark_catalog import build_benchmark_catalog_response
from .benchmark_composition import (
    benchmark_composition_definition_context,
    build_benchmark_composition_window_response,
)
from .benchmark_coverage import build_benchmark_coverage_response
from .benchmark_market_series import (
    benchmark_market_series_currency,
    benchmark_market_series_evidence_plan,
    benchmark_market_series_evidence_read_factories,
    benchmark_market_series_fx_context,
    benchmark_market_series_index_page,
    benchmark_market_series_page_token,
    benchmark_market_series_read_evidence,
    benchmark_market_series_request_scope,
    build_benchmark_market_series_response,
)
from .benchmark_return_series import build_benchmark_return_series_response
from .cio_model_change_cohort import build_cio_model_change_affected_cohort_response
from .classification_taxonomy import build_classification_taxonomy_response
from .client_income_needs_schedule import build_client_income_needs_schedule_response
from .client_restriction_profile import build_client_restriction_profile_response
from .client_tax_profile import build_client_tax_profile_response
from .client_tax_rule_set import build_client_tax_rule_set_response
from .discretionary_mandate_binding import build_discretionary_mandate_binding_response
from .dpm_portfolio_universe import (
    build_dpm_portfolio_universe_response,
    dpm_portfolio_universe_after_sort_key,
    dpm_portfolio_universe_next_page_token_payload,
    dpm_portfolio_universe_read_scope,
)
from .dpm_source_readiness import (
    build_dpm_source_readiness_response,
    dpm_eligibility_request,
    dpm_mandate_binding_request,
    dpm_market_data_coverage_request,
    dpm_model_targets_request,
    dpm_source_eligibility_family,
    dpm_source_eligibility_read_or_none,
    dpm_source_evaluated_instrument_ids,
    dpm_source_mandate_resolution,
    dpm_source_market_data_family,
    dpm_source_model_targets_read_or_none,
    dpm_source_model_targets_resolution,
    dpm_source_read_or_none,
    dpm_source_tax_lots_family,
    dpm_source_tax_lots_read_or_none,
    dpm_tax_lot_window_request,
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
    build_liquidity_reserve_requirement_response,
)
from .market_data_coverage import (
    build_market_data_coverage_response,
    market_data_coverage_read_scope,
)
from .model_portfolio_targets import build_model_portfolio_target_response
from .page_token_codec import PageTokenCodec
from .planned_withdrawal_schedule import build_planned_withdrawal_schedule_response
from .portfolio_manager_book_membership import (
    build_portfolio_manager_book_membership_response,
    portfolio_manager_book_membership_portfolio_types,
)
from .portfolio_tax_lot_window import (
    build_portfolio_tax_lot_window_response,
    portfolio_tax_lot_next_page_token_payload,
    portfolio_tax_lot_window_request_scope,
)
from .reference_data_mappers import benchmark_definition_response
from .risk_free_coverage import build_risk_free_coverage_response
from .risk_free_series import build_risk_free_series_response
from .sustainability_preference_profile import (
    build_sustainability_preference_profile_response,
)
from .transaction_cost_curve import (
    build_transaction_cost_curve_page,
    build_transaction_cost_curve_response,
    transaction_cost_curve_next_page_token_payload,
    transaction_cost_curve_request_scope,
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
        definition = await self._reference_repository.resolve_model_portfolio_definition(
            model_portfolio_id=model_portfolio_id,
            as_of_date=request.as_of_date,
        )
        if definition is None:
            return None

        targets = await self._reference_repository.list_model_portfolio_targets(
            model_portfolio_id=model_portfolio_id,
            model_portfolio_version=definition.model_portfolio_version,
            as_of_date=request.as_of_date,
            include_inactive_targets=request.include_inactive_targets,
        )
        return build_model_portfolio_target_response(
            definition=definition,
            request=request,
            target_rows=targets,
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
        definition = await self._reference_repository.resolve_model_portfolio_definition(
            model_portfolio_id=model_portfolio_id,
            as_of_date=request.as_of_date,
        )
        if definition is None:
            return None

        rows = await self._reference_repository.list_model_portfolio_affected_mandates(
            model_portfolio_id=model_portfolio_id,
            as_of_date=request.as_of_date,
            booking_center_code=request.booking_center_code,
            include_inactive_mandates=request.include_inactive_mandates,
        )
        return build_cio_model_change_affected_cohort_response(
            definition=definition,
            request=request,
            mandate_rows=rows,
        )

    async def resolve_dpm_portfolio_universe_candidates(
        self,
        request: DpmPortfolioUniverseCandidateRequest,
    ) -> DpmPortfolioUniverseCandidateResponse:
        read_scope = dpm_portfolio_universe_read_scope(request)
        cursor = self._decode_page_token(request.page.page_token)
        after_sort_key = dpm_portfolio_universe_after_sort_key(
            cursor=cursor,
            request_scope_fingerprint=read_scope.request_scope_fingerprint,
        )

        rows = await self._reference_repository.list_dpm_portfolio_universe_candidates(
            as_of_date=request.as_of_date,
            booking_center_code=read_scope.booking_center_code,
            model_portfolio_ids=read_scope.model_portfolio_ids,
            include_inactive_mandates=request.include_inactive_mandates,
            after_sort_key=after_sort_key,
            limit=request.page.page_size + 1,
        )
        has_more = len(rows) > request.page.page_size
        page_rows = rows[: request.page.page_size]

        next_page_token: str | None = None
        token_payload = dpm_portfolio_universe_next_page_token_payload(
            request_scope_fingerprint=read_scope.request_scope_fingerprint,
            page_rows=page_rows,
            has_more=has_more,
        )
        if token_payload:
            next_page_token = self._encode_page_token(token_payload)

        return build_dpm_portfolio_universe_response(
            request=request,
            read_scope=read_scope,
            page_rows=page_rows,
            has_more=has_more,
            next_page_token=next_page_token,
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
        binding = await self._reference_repository.resolve_discretionary_mandate_binding(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            mandate_id=request.mandate_id,
        )
        if binding is None:
            return None

        rows = await self._reference_repository.list_client_restriction_profiles(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            as_of_date=request.as_of_date,
            mandate_id=binding.mandate_id,
            include_inactive_restrictions=request.include_inactive_restrictions,
        )
        return build_client_restriction_profile_response(
            portfolio_id=portfolio_id,
            binding=binding,
            request=request,
            rows=rows,
        )

    async def get_sustainability_preference_profile(
        self,
        portfolio_id: str,
        request: SustainabilityPreferenceProfileRequest,
    ) -> SustainabilityPreferenceProfileResponse | None:
        binding = await self._reference_repository.resolve_discretionary_mandate_binding(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            mandate_id=request.mandate_id,
        )
        if binding is None:
            return None

        rows = await self._reference_repository.list_sustainability_preference_profiles(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            as_of_date=request.as_of_date,
            mandate_id=binding.mandate_id,
            include_inactive_preferences=request.include_inactive_preferences,
        )
        return build_sustainability_preference_profile_response(
            portfolio_id=portfolio_id,
            binding=binding,
            request=request,
            rows=rows,
        )

    async def get_client_tax_profile(
        self,
        portfolio_id: str,
        request: ClientTaxProfileRequest,
    ) -> ClientTaxProfileResponse | None:
        binding = await self._reference_repository.resolve_discretionary_mandate_binding(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            mandate_id=request.mandate_id,
        )
        if binding is None:
            return None

        rows = await self._reference_repository.list_client_tax_profiles(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            as_of_date=request.as_of_date,
            mandate_id=binding.mandate_id,
            include_inactive_profiles=request.include_inactive_profiles,
        )
        return build_client_tax_profile_response(
            portfolio_id=portfolio_id,
            binding=binding,
            request=request,
            rows=rows,
        )

    async def get_client_tax_rule_set(
        self,
        portfolio_id: str,
        request: ClientTaxRuleSetRequest,
    ) -> ClientTaxRuleSetResponse | None:
        binding = await self._reference_repository.resolve_discretionary_mandate_binding(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            mandate_id=request.mandate_id,
        )
        if binding is None:
            return None

        rows = await self._reference_repository.list_client_tax_rule_sets(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            as_of_date=request.as_of_date,
            mandate_id=binding.mandate_id,
            include_inactive_rules=request.include_inactive_rules,
        )
        return build_client_tax_rule_set_response(
            portfolio_id=portfolio_id,
            binding=binding,
            request=request,
            rows=rows,
        )

    async def get_client_income_needs_schedule(
        self,
        portfolio_id: str,
        request: ClientIncomeNeedsScheduleRequest,
    ) -> ClientIncomeNeedsScheduleResponse | None:
        binding = await self._reference_repository.resolve_discretionary_mandate_binding(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            mandate_id=request.mandate_id,
        )
        if binding is None:
            return None

        rows = await self._reference_repository.list_client_income_needs_schedules(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            as_of_date=request.as_of_date,
            mandate_id=binding.mandate_id,
            include_inactive_schedules=request.include_inactive_schedules,
        )
        return build_client_income_needs_schedule_response(
            portfolio_id=portfolio_id,
            binding=binding,
            request=request,
            rows=rows,
        )

    async def get_liquidity_reserve_requirement(
        self,
        portfolio_id: str,
        request: LiquidityReserveRequirementRequest,
    ) -> LiquidityReserveRequirementResponse | None:
        binding = await self._reference_repository.resolve_discretionary_mandate_binding(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            mandate_id=request.mandate_id,
        )
        if binding is None:
            return None

        rows = await self._reference_repository.list_liquidity_reserve_requirements(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            as_of_date=request.as_of_date,
            mandate_id=binding.mandate_id,
            include_inactive_requirements=request.include_inactive_requirements,
        )
        return build_liquidity_reserve_requirement_response(
            portfolio_id=portfolio_id,
            binding=binding,
            request=request,
            rows=rows,
        )

    async def get_planned_withdrawal_schedule(
        self,
        portfolio_id: str,
        request: PlannedWithdrawalScheduleRequest,
    ) -> PlannedWithdrawalScheduleResponse | None:
        binding = await self._reference_repository.resolve_discretionary_mandate_binding(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            mandate_id=request.mandate_id,
        )
        if binding is None:
            return None

        rows = await self._reference_repository.list_planned_withdrawal_schedules(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            as_of_date=request.as_of_date,
            horizon_days=request.horizon_days,
            mandate_id=binding.mandate_id,
            include_inactive_withdrawals=request.include_inactive_withdrawals,
        )
        return build_planned_withdrawal_schedule_response(
            portfolio_id=portfolio_id,
            binding=binding,
            request=request,
            rows=rows,
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
        if not await self._buy_state_repository.portfolio_exists(portfolio_id):
            raise LookupError(f"Portfolio with id {portfolio_id} not found")

        request_scope = portfolio_tax_lot_window_request_scope(
            portfolio_id=portfolio_id,
            request=request,
            cursor=self._decode_page_token(request.page.page_token),
        )

        rows = await self._buy_state_repository.list_portfolio_tax_lots(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            security_ids=request.security_ids,
            include_closed_lots=request.include_closed_lots,
            lot_status_filter=request.lot_status_filter,
            after_sort_key=request_scope.after_sort_key,
            limit=request.page.page_size + 1,
        )
        has_more = len(rows) > request.page.page_size
        page_rows = rows[: request.page.page_size]

        next_page_token: str | None = None
        next_page_token_payload = portfolio_tax_lot_next_page_token_payload(
            request_scope=request_scope,
            has_more=has_more,
            page_rows=page_rows,
        )
        if next_page_token_payload is not None:
            next_page_token = self._encode_page_token(next_page_token_payload)

        return build_portfolio_tax_lot_window_response(
            portfolio_id=portfolio_id,
            request=request,
            request_scope_fingerprint=request_scope.request_fingerprint,
            page_rows=page_rows,
            has_more=has_more,
            next_page_token=next_page_token,
        )

    async def get_transaction_cost_curve(
        self,
        *,
        portfolio_id: str,
        request: TransactionCostCurveRequest,
    ) -> TransactionCostCurveResponse:
        if not await self._transaction_repository.portfolio_exists(portfolio_id):
            raise LookupError(f"Portfolio with id {portfolio_id} not found")

        request_scope = transaction_cost_curve_request_scope(
            portfolio_id=portfolio_id,
            request=request,
            cursor=self._decode_page_token(request.page.page_token),
        )

        transactions = await self._transaction_repository.list_transaction_cost_evidence(
            portfolio_id=portfolio_id,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
            as_of_date=request.as_of_date,
            security_ids=request.security_ids,
            transaction_types=request.transaction_types,
        )

        curve_page = build_transaction_cost_curve_page(
            portfolio_id=portfolio_id,
            transactions=transactions,
            min_observation_count=request.min_observation_count,
            after_key=request_scope.after_key,
            page_size=request.page.page_size,
        )

        next_page_token: str | None = None
        next_page_token_payload = transaction_cost_curve_next_page_token_payload(
            request_scope=request_scope,
            curve_page=curve_page,
        )
        if next_page_token_payload is not None:
            next_page_token = self._encode_page_token(next_page_token_payload)

        return build_transaction_cost_curve_response(
            portfolio_id=portfolio_id,
            request=request,
            request_scope_fingerprint=request_scope.request_fingerprint,
            curve_page=curve_page,
            transactions=transactions,
            next_page_token=next_page_token,
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
        families: list[DpmSourceFamilyReadiness] = []

        mandate_response = await dpm_source_read_or_none(
            lambda: self.resolve_discretionary_mandate_binding(
                portfolio_id,
                dpm_mandate_binding_request(request),
            )
        )
        mandate_resolution = dpm_source_mandate_resolution(
            request=request,
            mandate_response=mandate_response,
        )
        resolved_identity = mandate_resolution.identity
        families.append(mandate_resolution.family)

        model_response = await dpm_source_model_targets_read_or_none(
            model_portfolio_id=resolved_identity.model_portfolio_id,
            read_model_targets=lambda model_portfolio_id: self.resolve_model_portfolio_targets(
                model_portfolio_id,
                dpm_model_targets_request(request),
            ),
        )
        model_targets = dpm_source_model_targets_resolution(
            model_portfolio_id=resolved_identity.model_portfolio_id,
            model_response=model_response,
        )
        target_instrument_ids = model_targets.target_instrument_ids
        families.append(model_targets.family)

        evaluated_instrument_ids = dpm_source_evaluated_instrument_ids(
            request_instrument_ids=request.instrument_ids,
            target_instrument_ids=target_instrument_ids,
        )
        eligibility = await dpm_source_eligibility_read_or_none(
            evaluated_instrument_ids=evaluated_instrument_ids,
            read_eligibility=lambda instrument_ids: self.resolve_instrument_eligibility_bulk(
                dpm_eligibility_request(
                    request=request,
                    instrument_ids=instrument_ids,
                )
            ),
        )
        families.append(
            dpm_source_eligibility_family(
                evaluated_instrument_ids=evaluated_instrument_ids,
                eligibility_response=eligibility,
            )
        )

        tax_lots = await dpm_source_tax_lots_read_or_none(
            portfolio_id=portfolio_id,
            evaluated_instrument_ids=evaluated_instrument_ids,
            read_tax_lots=lambda scoped_portfolio_id, instrument_ids: (
                self.get_portfolio_tax_lot_window(
                    portfolio_id=scoped_portfolio_id,
                    request=dpm_tax_lot_window_request(
                        request=request,
                        evaluated_instrument_ids=instrument_ids,
                    ),
                )
            ),
        )
        families.append(
            dpm_source_tax_lots_family(
                portfolio_id=portfolio_id,
                tax_lot_response=tax_lots,
            )
        )

        market_data: MarketDataCoverageWindowResponse | None = None
        market_data = await dpm_source_read_or_none(
            lambda: self.get_market_data_coverage(
                dpm_market_data_coverage_request(
                    request=request,
                    evaluated_instrument_ids=evaluated_instrument_ids,
                )
            )
        )
        families.append(dpm_source_market_data_family(market_data))

        return build_dpm_source_readiness_response(
            portfolio_id=portfolio_id,
            request=request,
            resolved_mandate_id=resolved_identity.mandate_id,
            resolved_model_portfolio_id=resolved_identity.model_portfolio_id,
            evaluated_instrument_ids=evaluated_instrument_ids,
            families=families,
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
        definition_rows = (
            await self._reference_repository.list_benchmark_definitions_overlapping_window(
                benchmark_id=benchmark_id,
                start_date=request.window.start_date,
                end_date=request.window.end_date,
            )
        )
        definition_context = benchmark_composition_definition_context(definition_rows)
        if definition_context is None:
            return None

        component_rows = (
            await self._reference_repository.list_benchmark_components_overlapping_window(
                benchmark_id=benchmark_id,
                start_date=request.window.start_date,
                end_date=request.window.end_date,
            )
        )
        return build_benchmark_composition_window_response(
            benchmark_id=benchmark_id,
            request=request,
            definition_context=definition_context,
            component_rows=component_rows,
        )

    async def list_benchmark_catalog(
        self,
        as_of_date: date,
        benchmark_type: str | None,
        benchmark_currency: str | None,
        benchmark_status: str | None,
    ) -> BenchmarkCatalogResponse:
        rows = await self._reference_repository.list_benchmark_definitions(
            as_of_date=as_of_date,
            benchmark_type=benchmark_type,
            benchmark_currency=benchmark_currency,
            benchmark_status=benchmark_status,
        )
        components_by_benchmark = (
            await self._reference_repository.list_benchmark_components_for_benchmarks(
                benchmark_ids=[row.benchmark_id for row in rows],
                as_of_date=as_of_date,
            )
        )
        return build_benchmark_catalog_response(
            as_of_date=as_of_date,
            rows=rows,
            components_by_benchmark=components_by_benchmark,
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
        definition = await self._reference_repository.get_benchmark_definition(
            benchmark_id, request.as_of_date
        )
        benchmark_currency = benchmark_market_series_currency(
            definition=definition,
            target_currency=request.target_currency,
        )
        page = getattr(request, "page", None)
        page_token = getattr(page, "page_token", None)
        request_scope = benchmark_market_series_request_scope(
            benchmark_id=benchmark_id,
            request=request,
            cursor=self._decode_page_token(page_token),
        )
        candidate_index_ids = (
            await self._reference_repository.list_benchmark_component_index_ids_overlapping_window(
                benchmark_id=benchmark_id,
                start_date=request.window.start_date,
                end_date=request.window.end_date,
                after_index_id=request_scope.cursor_index_id,
                limit=request_scope.page_size + 1,
            )
        )
        index_page = benchmark_market_series_index_page(
            candidate_index_ids=candidate_index_ids,
            page_size=request_scope.page_size,
        )
        fx_context = benchmark_market_series_fx_context(
            benchmark_currency=benchmark_currency,
            target_currency=request.target_currency,
            requested_fields=request_scope.requested_fields,
        )
        evidence_plan = benchmark_market_series_evidence_plan(
            requested_fields=request_scope.requested_fields,
            fx_context=fx_context,
        )
        market_results = await benchmark_market_series_read_evidence(
            evidence_plan=evidence_plan,
            read_factories=benchmark_market_series_evidence_read_factories(
                repository=self._reference_repository,
                benchmark_id=benchmark_id,
                request=request,
                benchmark_currency=benchmark_currency,
                index_ids=index_page.index_ids,
            ),
        )
        next_page_token = benchmark_market_series_page_token(
            request_scope=request_scope,
            has_more=index_page.has_more,
            index_ids=index_page.index_ids,
            encode_page_token=self._encode_page_token,
        )

        return build_benchmark_market_series_response(
            benchmark_id=benchmark_id,
            request=request,
            benchmark_currency=benchmark_currency,
            request_scope_fingerprint=request_scope.request_fingerprint,
            page_size=request_scope.page_size,
            has_more=index_page.has_more,
            next_page_token=next_page_token,
            index_ids=index_page.index_ids,
            component_rows=market_results["components"],
            index_prices=market_results.get("index_prices", []),
            index_returns=market_results.get("index_returns", []),
            benchmark_returns=market_results.get("benchmark_returns", []),
            fx_rates=market_results.get("fx_rates", {}),
            fx_context=fx_context,
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
