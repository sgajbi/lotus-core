import logging
from datetime import UTC, date, datetime
from typing import Any, Literal, cast

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
    ClientIncomeNeedsScheduleSupportability,
    ClientRestrictionProfileRequest,
    ClientRestrictionProfileResponse,
    ClientTaxProfileRequest,
    ClientTaxProfileResponse,
    ClientTaxProfileSupportability,
    ClientTaxRuleSetRequest,
    ClientTaxRuleSetResponse,
    ClientTaxRuleSetSupportability,
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
    ExternalCurrencyExposureSupportability,
    ExternalEligibleHedgeInstrumentRequest,
    ExternalEligibleHedgeInstrumentResponse,
    ExternalEligibleHedgeInstrumentSupportability,
    ExternalFXForwardCurveRequest,
    ExternalFXForwardCurveResponse,
    ExternalFXForwardCurveSupportability,
    ExternalHedgeExecutionReadinessRequest,
    ExternalHedgeExecutionReadinessResponse,
    ExternalHedgeExecutionReadinessSupportability,
    ExternalHedgePolicyRequest,
    ExternalHedgePolicyResponse,
    ExternalHedgePolicySupportability,
    ExternalOrderExecutionAcknowledgementRequest,
    ExternalOrderExecutionAcknowledgementResponse,
    ExternalOrderExecutionAcknowledgementSupportability,
    IndexCatalogResponse,
    IndexPriceSeriesResponse,
    IndexReturnSeriesResponse,
    IndexSeriesRequest,
    InstrumentEligibilityBulkRequest,
    InstrumentEligibilityBulkResponse,
    IntegrationWindow,
    LiquidityReserveRequirementRequest,
    LiquidityReserveRequirementResponse,
    LiquidityReserveRequirementSupportability,
    MarketDataCoverageRequest,
    MarketDataCoverageWindowResponse,
    ModelPortfolioTargetRequest,
    ModelPortfolioTargetResponse,
    PlannedWithdrawalScheduleRequest,
    PlannedWithdrawalScheduleResponse,
    PlannedWithdrawalScheduleSupportability,
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
from ..dtos.source_data_product_identity import source_data_product_runtime_metadata
from ..repositories.buy_state_repository import BuyStateRepository
from ..repositories.currency_codes import normalize_currency_code
from ..repositories.portfolio_repository import PortfolioRepository
from ..repositories.reference_data_repository import ReferenceDataRepository
from ..repositories.transaction_repository import TransactionRepository
from ..settings import load_query_service_settings
from .benchmark_composition import (
    benchmark_composition_definition_context,
    build_benchmark_composition_window_response,
)
from .benchmark_market_series import (
    benchmark_market_series_fx_context,
    build_benchmark_market_series_response,
)
from .cio_model_change_cohort import build_cio_model_change_affected_cohort_response
from .client_restriction_profile import build_client_restriction_profile_response
from .discretionary_mandate_binding import build_discretionary_mandate_binding_response
from .dpm_portfolio_universe import (
    build_dpm_portfolio_universe_response,
    dpm_portfolio_universe_after_sort_key,
    dpm_portfolio_universe_next_page_token_payload,
    dpm_portfolio_universe_read_scope,
)
from .dpm_source_readiness import (
    build_dpm_source_readiness_response,
    dpm_source_family_readiness,
    unavailable_dpm_source_family,
)
from .instrument_eligibility import build_instrument_eligibility_bulk_response
from .integration_policy import build_effective_policy_response
from .market_data_coverage import (
    build_market_data_coverage_response,
    market_data_coverage_read_scope,
)
from .market_reference_coverage import market_reference_coverage_response
from .model_portfolio_targets import build_model_portfolio_target_response
from .page_token_codec import PageTokenCodec
from .portfolio_manager_book_membership import (
    build_portfolio_manager_book_membership_response,
    portfolio_manager_book_membership_portfolio_types,
)
from .portfolio_tax_lot_window import (
    build_portfolio_tax_lot_window_response,
    portfolio_tax_lot_after_sort_key,
)
from .reference_data_helpers import (
    latest_reference_evidence_timestamp,
    market_reference_data_quality_status,
)
from .reference_data_mappers import (
    benchmark_definition_response,
    benchmark_return_series_point,
    classification_taxonomy_entry,
    client_income_needs_schedule_entry,
    client_tax_profile_entry,
    client_tax_rule_set_entry,
    index_definition_response,
    index_price_series_point,
    index_return_series_point,
    liquidity_reserve_requirement_entry,
    planned_withdrawal_schedule_entry,
    risk_free_series_point,
)
from .request_fingerprint import (
    request_fingerprint as build_request_fingerprint,
)
from .request_fingerprint import (
    series_request_fingerprint,
)
from .source_data_runtime import (
    source_product_runtime_metadata,
    source_product_runtime_metadata_without_as_of_date,
)
from .sustainability_preference_profile import (
    build_sustainability_preference_profile_response,
)
from .transaction_cost_curve import (
    build_transaction_cost_curve_page,
    build_transaction_cost_curve_response,
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
        return BenchmarkAssignmentResponse(
            portfolio_id=row.portfolio_id,
            benchmark_id=row.benchmark_id,
            as_of_date=as_of_date,
            effective_from=row.effective_from,
            effective_to=row.effective_to,
            assignment_source=row.assignment_source,
            assignment_status=row.assignment_status,
            policy_pack_id=row.policy_pack_id,
            source_system=row.source_system,
            assignment_recorded_at=row.assignment_recorded_at,
            assignment_version=int(row.assignment_version),
            **source_product_runtime_metadata_without_as_of_date(
                as_of_date,
                data_quality_status="COMPLETE",
                latest_evidence_timestamp=latest_reference_evidence_timestamp([row]),
            ),
        )

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
        entries = [client_tax_profile_entry(row) for row in rows]
        supportability_state: Literal["READY", "INCOMPLETE", "UNAVAILABLE"] = "READY"
        supportability_reason = "CLIENT_TAX_PROFILE_READY"
        missing_data_families: list[str] = []
        if not rows:
            supportability_state = "INCOMPLETE"
            supportability_reason = "CLIENT_TAX_PROFILE_EMPTY"
            missing_data_families.append("client_tax_profile")

        latest_evidence_timestamp = latest_reference_evidence_timestamp([binding], rows)
        return ClientTaxProfileResponse(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            mandate_id=binding.mandate_id,
            profiles=entries,
            supportability=ClientTaxProfileSupportability(
                state=supportability_state,
                reason=supportability_reason,
                profile_count=len(entries),
                missing_data_families=missing_data_families,
            ),
            lineage={
                "source_system": "lotus-core-query-service",
                "source_table": "client_tax_profiles,portfolio_mandate_bindings",
                "contract_version": "rfc_042_client_tax_profile_v1",
            },
            **source_data_product_runtime_metadata(
                as_of_date=request.as_of_date,
                tenant_id=request.tenant_id,
                data_quality_status=("ACCEPTED" if rows else "MISSING"),
                latest_evidence_timestamp=latest_evidence_timestamp,
                source_batch_fingerprint=build_request_fingerprint(
                    {
                        "product": "ClientTaxProfile",
                        "portfolio_id": portfolio_id,
                        "client_id": binding.client_id,
                        "mandate_id": binding.mandate_id,
                        "as_of_date": request.as_of_date.isoformat(),
                        "row_count": len(rows),
                    }
                ),
                snapshot_id=(
                    "client_tax_profile:"
                    + build_request_fingerprint(
                        {
                            "portfolio_id": portfolio_id,
                            "client_id": binding.client_id,
                            "as_of_date": request.as_of_date.isoformat(),
                        }
                    )
                ),
            ),
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
        entries = [client_tax_rule_set_entry(row) for row in rows]
        supportability_state: Literal["READY", "INCOMPLETE", "UNAVAILABLE"] = "READY"
        supportability_reason = "CLIENT_TAX_RULE_SET_READY"
        missing_data_families: list[str] = []
        if not rows:
            supportability_state = "INCOMPLETE"
            supportability_reason = "CLIENT_TAX_RULE_SET_EMPTY"
            missing_data_families.append("client_tax_rule_set")

        latest_evidence_timestamp = latest_reference_evidence_timestamp([binding], rows)
        return ClientTaxRuleSetResponse(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            mandate_id=binding.mandate_id,
            rules=entries,
            supportability=ClientTaxRuleSetSupportability(
                state=supportability_state,
                reason=supportability_reason,
                rule_count=len(entries),
                missing_data_families=missing_data_families,
            ),
            lineage={
                "source_system": "lotus-core-query-service",
                "source_table": "client_tax_rule_sets,portfolio_mandate_bindings",
                "contract_version": "rfc_042_client_tax_rule_set_v1",
            },
            **source_data_product_runtime_metadata(
                as_of_date=request.as_of_date,
                tenant_id=request.tenant_id,
                data_quality_status=("ACCEPTED" if rows else "MISSING"),
                latest_evidence_timestamp=latest_evidence_timestamp,
                source_batch_fingerprint=build_request_fingerprint(
                    {
                        "product": "ClientTaxRuleSet",
                        "portfolio_id": portfolio_id,
                        "client_id": binding.client_id,
                        "mandate_id": binding.mandate_id,
                        "as_of_date": request.as_of_date.isoformat(),
                        "row_count": len(rows),
                    }
                ),
                snapshot_id=(
                    "client_tax_rule_set:"
                    + build_request_fingerprint(
                        {
                            "portfolio_id": portfolio_id,
                            "client_id": binding.client_id,
                            "as_of_date": request.as_of_date.isoformat(),
                        }
                    )
                ),
            ),
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
        entries = [client_income_needs_schedule_entry(row) for row in rows]
        supportability_state: Literal["READY", "INCOMPLETE", "UNAVAILABLE"] = "READY"
        supportability_reason = "CLIENT_INCOME_NEEDS_SCHEDULE_READY"
        missing_data_families: list[str] = []
        if not rows:
            supportability_state = "INCOMPLETE"
            supportability_reason = "CLIENT_INCOME_NEEDS_SCHEDULE_EMPTY"
            missing_data_families.append("client_income_needs_schedule")

        latest_evidence_timestamp = latest_reference_evidence_timestamp([binding], rows)
        return ClientIncomeNeedsScheduleResponse(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            mandate_id=binding.mandate_id,
            schedules=entries,
            supportability=ClientIncomeNeedsScheduleSupportability(
                state=supportability_state,
                reason=supportability_reason,
                schedule_count=len(entries),
                missing_data_families=missing_data_families,
            ),
            lineage={
                "source_system": "lotus-core-query-service",
                "source_table": "client_income_needs_schedules,portfolio_mandate_bindings",
                "contract_version": "rfc_042_client_income_needs_schedule_v1",
            },
            **source_data_product_runtime_metadata(
                as_of_date=request.as_of_date,
                tenant_id=request.tenant_id,
                data_quality_status=("ACCEPTED" if rows else "MISSING"),
                latest_evidence_timestamp=latest_evidence_timestamp,
                source_batch_fingerprint=build_request_fingerprint(
                    {
                        "product": "ClientIncomeNeedsSchedule",
                        "portfolio_id": portfolio_id,
                        "client_id": binding.client_id,
                        "mandate_id": binding.mandate_id,
                        "as_of_date": request.as_of_date.isoformat(),
                        "row_count": len(rows),
                    }
                ),
                snapshot_id=(
                    "client_income_needs_schedule:"
                    + build_request_fingerprint(
                        {
                            "portfolio_id": portfolio_id,
                            "client_id": binding.client_id,
                            "as_of_date": request.as_of_date.isoformat(),
                        }
                    )
                ),
            ),
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
        entries = [liquidity_reserve_requirement_entry(row) for row in rows]
        supportability_state: Literal["READY", "INCOMPLETE", "UNAVAILABLE"] = "READY"
        supportability_reason = "LIQUIDITY_RESERVE_REQUIREMENT_READY"
        missing_data_families: list[str] = []
        if not rows:
            supportability_state = "INCOMPLETE"
            supportability_reason = "LIQUIDITY_RESERVE_REQUIREMENT_EMPTY"
            missing_data_families.append("liquidity_reserve_requirement")

        latest_evidence_timestamp = latest_reference_evidence_timestamp([binding], rows)
        return LiquidityReserveRequirementResponse(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            mandate_id=binding.mandate_id,
            requirements=entries,
            supportability=LiquidityReserveRequirementSupportability(
                state=supportability_state,
                reason=supportability_reason,
                requirement_count=len(entries),
                missing_data_families=missing_data_families,
            ),
            lineage={
                "source_system": "lotus-core-query-service",
                "source_table": "liquidity_reserve_requirements,portfolio_mandate_bindings",
                "contract_version": "rfc_042_liquidity_reserve_requirement_v1",
            },
            **source_data_product_runtime_metadata(
                as_of_date=request.as_of_date,
                tenant_id=request.tenant_id,
                data_quality_status=("ACCEPTED" if rows else "MISSING"),
                latest_evidence_timestamp=latest_evidence_timestamp,
                source_batch_fingerprint=build_request_fingerprint(
                    {
                        "product": "LiquidityReserveRequirement",
                        "portfolio_id": portfolio_id,
                        "client_id": binding.client_id,
                        "mandate_id": binding.mandate_id,
                        "as_of_date": request.as_of_date.isoformat(),
                        "row_count": len(rows),
                    }
                ),
                snapshot_id=(
                    "liquidity_reserve_requirement:"
                    + build_request_fingerprint(
                        {
                            "portfolio_id": portfolio_id,
                            "client_id": binding.client_id,
                            "as_of_date": request.as_of_date.isoformat(),
                        }
                    )
                ),
            ),
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
        entries = [planned_withdrawal_schedule_entry(row) for row in rows]
        supportability_state: Literal["READY", "INCOMPLETE", "UNAVAILABLE"] = "READY"
        supportability_reason = "PLANNED_WITHDRAWAL_SCHEDULE_READY"
        missing_data_families: list[str] = []
        if not rows:
            supportability_state = "INCOMPLETE"
            supportability_reason = "PLANNED_WITHDRAWAL_SCHEDULE_EMPTY"
            missing_data_families.append("planned_withdrawal_schedule")

        latest_evidence_timestamp = latest_reference_evidence_timestamp([binding], rows)
        return PlannedWithdrawalScheduleResponse(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            mandate_id=binding.mandate_id,
            horizon_days=request.horizon_days,
            withdrawals=entries,
            supportability=PlannedWithdrawalScheduleSupportability(
                state=supportability_state,
                reason=supportability_reason,
                withdrawal_count=len(entries),
                missing_data_families=missing_data_families,
            ),
            lineage={
                "source_system": "lotus-core-query-service",
                "source_table": "planned_withdrawal_schedules,portfolio_mandate_bindings",
                "contract_version": "rfc_042_planned_withdrawal_schedule_v1",
            },
            **source_data_product_runtime_metadata(
                as_of_date=request.as_of_date,
                tenant_id=request.tenant_id,
                data_quality_status=("ACCEPTED" if rows else "MISSING"),
                latest_evidence_timestamp=latest_evidence_timestamp,
                source_batch_fingerprint=build_request_fingerprint(
                    {
                        "product": "PlannedWithdrawalSchedule",
                        "portfolio_id": portfolio_id,
                        "client_id": binding.client_id,
                        "mandate_id": binding.mandate_id,
                        "as_of_date": request.as_of_date.isoformat(),
                        "horizon_days": request.horizon_days,
                        "row_count": len(rows),
                    }
                ),
                snapshot_id=(
                    "planned_withdrawal_schedule:"
                    + build_request_fingerprint(
                        {
                            "portfolio_id": portfolio_id,
                            "client_id": binding.client_id,
                            "as_of_date": request.as_of_date.isoformat(),
                            "horizon_days": request.horizon_days,
                        }
                    )
                ),
            ),
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

        missing_data_families = [
            "external_currency_exposure",
            "external_hedge_policy",
            "external_fx_forward_curve",
            "external_eligible_hedge_instrument",
            "external_hedge_execution_readiness",
        ]
        blocked_capabilities = [
            "hedge_advice",
            "forward_pricing",
            "counterparty_selection",
            "best_execution",
            "oms_acknowledgement",
            "fills",
            "settlement",
            "autonomous_treasury_action",
        ]

        return ExternalHedgeExecutionReadinessResponse(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            mandate_id=binding.mandate_id,
            reporting_currency=request.reporting_currency,
            exposure_currencies=request.exposure_currencies,
            readiness_checks=[],
            supportability=ExternalHedgeExecutionReadinessSupportability(
                missing_data_families=missing_data_families,
                blocked_capabilities=blocked_capabilities,
            ),
            lineage={
                "source_system": "external-bank-treasury",
                "source_table": "not_ingested",
                "contract_version": "rfc_039_external_hedge_execution_readiness_v1",
                "integration_status": "not_ingested",
                "runtime_posture": "fail_closed",
                "non_claims": ",".join(blocked_capabilities),
            },
            **source_data_product_runtime_metadata(
                as_of_date=request.as_of_date,
                tenant_id=request.tenant_id,
                data_quality_status="MISSING",
                latest_evidence_timestamp=None,
                source_batch_fingerprint=build_request_fingerprint(
                    {
                        "product": "ExternalHedgeExecutionReadiness",
                        "portfolio_id": portfolio_id,
                        "client_id": binding.client_id,
                        "mandate_id": binding.mandate_id,
                        "as_of_date": request.as_of_date.isoformat(),
                        "reporting_currency": request.reporting_currency,
                        "exposure_currencies": sorted(request.exposure_currencies),
                        "integration_status": "not_ingested",
                    }
                ),
                snapshot_id=(
                    "external_hedge_execution_readiness:"
                    + build_request_fingerprint(
                        {
                            "portfolio_id": portfolio_id,
                            "client_id": binding.client_id,
                            "as_of_date": request.as_of_date.isoformat(),
                            "integration_status": "not_ingested",
                        }
                    )
                ),
            ),
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

        missing_data_families = [
            "external_currency_exposure",
            "external_hedge_policy",
            "external_fx_forward_curve",
            "external_eligible_hedge_instrument",
        ]
        blocked_capabilities = [
            "fx_attribution",
            "hedge_advice",
            "treasury_instruction",
            "execution_readiness",
            "oms_acknowledgement",
            "fills",
            "settlement",
            "autonomous_treasury_action",
        ]

        return ExternalCurrencyExposureResponse(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            mandate_id=binding.mandate_id,
            reporting_currency=request.reporting_currency,
            exposure_currencies=request.exposure_currencies,
            exposures=[],
            supportability=ExternalCurrencyExposureSupportability(
                exposure_count=0,
                missing_data_families=missing_data_families,
                blocked_capabilities=blocked_capabilities,
            ),
            lineage={
                "source_system": "external-bank-treasury",
                "source_table": "not_ingested",
                "contract_version": "rfc_039_external_currency_exposure_v1",
                "integration_status": "not_ingested",
                "runtime_posture": "fail_closed",
                "non_claims": ",".join(blocked_capabilities),
            },
            **source_data_product_runtime_metadata(
                as_of_date=request.as_of_date,
                tenant_id=request.tenant_id,
                data_quality_status="MISSING",
                latest_evidence_timestamp=None,
                source_batch_fingerprint=build_request_fingerprint(
                    {
                        "product": "ExternalCurrencyExposure",
                        "portfolio_id": portfolio_id,
                        "client_id": binding.client_id,
                        "mandate_id": binding.mandate_id,
                        "as_of_date": request.as_of_date.isoformat(),
                        "reporting_currency": request.reporting_currency,
                        "exposure_currencies": sorted(request.exposure_currencies),
                        "integration_status": "not_ingested",
                    }
                ),
                snapshot_id=(
                    "external_currency_exposure:"
                    + build_request_fingerprint(
                        {
                            "portfolio_id": portfolio_id,
                            "client_id": binding.client_id,
                            "as_of_date": request.as_of_date.isoformat(),
                            "integration_status": "not_ingested",
                        }
                    )
                ),
            ),
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

        missing_data_families = ["external_oms_order_execution_acknowledgement"]
        blocked_capabilities = [
            "order_generation",
            "venue_routing",
            "best_execution",
            "oms_acknowledgement",
            "fills",
            "settlement",
            "execution_status_certification",
            "autonomous_execution_action",
        ]

        return ExternalOrderExecutionAcknowledgementResponse(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            mandate_id=binding.mandate_id,
            execution_intent_id=request.execution_intent_id,
            order_reference_ids=request.order_reference_ids,
            acknowledgements=[],
            supportability=ExternalOrderExecutionAcknowledgementSupportability(
                acknowledgement_count=0,
                missing_data_families=missing_data_families,
                blocked_capabilities=blocked_capabilities,
            ),
            lineage={
                "source_system": "external-bank-oms",
                "source_table": "not_ingested",
                "contract_version": "rfc_042_external_order_execution_acknowledgement_v1",
                "integration_status": "not_ingested",
                "runtime_posture": "fail_closed",
                "non_claims": ",".join(blocked_capabilities),
            },
            **source_data_product_runtime_metadata(
                as_of_date=request.as_of_date,
                tenant_id=request.tenant_id,
                data_quality_status="MISSING",
                latest_evidence_timestamp=None,
                source_batch_fingerprint=build_request_fingerprint(
                    {
                        "product": "ExternalOrderExecutionAcknowledgement",
                        "portfolio_id": portfolio_id,
                        "client_id": binding.client_id,
                        "mandate_id": binding.mandate_id,
                        "as_of_date": request.as_of_date.isoformat(),
                        "execution_intent_id": request.execution_intent_id,
                        "order_reference_ids": sorted(request.order_reference_ids),
                        "integration_status": "not_ingested",
                    }
                ),
                snapshot_id=(
                    "external_order_execution_acknowledgement:"
                    + build_request_fingerprint(
                        {
                            "portfolio_id": portfolio_id,
                            "client_id": binding.client_id,
                            "as_of_date": request.as_of_date.isoformat(),
                            "execution_intent_id": request.execution_intent_id,
                            "order_reference_ids": sorted(request.order_reference_ids),
                            "integration_status": "not_ingested",
                        }
                    )
                ),
            ),
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

        missing_data_families = ["external_hedge_policy"]
        blocked_capabilities = [
            "hedge_policy_approval",
            "hedge_advice",
            "treasury_instruction",
            "counterparty_selection",
            "order_generation",
            "best_execution",
            "oms_acknowledgement",
            "fills",
            "settlement",
            "autonomous_treasury_action",
        ]

        return ExternalHedgePolicyResponse(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            mandate_id=binding.mandate_id,
            reporting_currency=request.reporting_currency,
            exposure_currencies=request.exposure_currencies,
            policy_rules=[],
            supportability=ExternalHedgePolicySupportability(
                policy_rule_count=0,
                missing_data_families=missing_data_families,
                blocked_capabilities=blocked_capabilities,
            ),
            lineage={
                "source_system": "external-bank-treasury",
                "source_table": "not_ingested",
                "contract_version": "rfc_039_external_hedge_policy_v1",
                "integration_status": "not_ingested",
                "runtime_posture": "fail_closed",
                "non_claims": ",".join(blocked_capabilities),
            },
            **source_data_product_runtime_metadata(
                as_of_date=request.as_of_date,
                tenant_id=request.tenant_id,
                data_quality_status="MISSING",
                latest_evidence_timestamp=None,
                source_batch_fingerprint=build_request_fingerprint(
                    {
                        "product": "ExternalHedgePolicy",
                        "portfolio_id": portfolio_id,
                        "client_id": binding.client_id,
                        "mandate_id": binding.mandate_id,
                        "as_of_date": request.as_of_date.isoformat(),
                        "reporting_currency": request.reporting_currency,
                        "exposure_currencies": sorted(request.exposure_currencies),
                        "integration_status": "not_ingested",
                    }
                ),
                snapshot_id=(
                    "external_hedge_policy:"
                    + build_request_fingerprint(
                        {
                            "portfolio_id": portfolio_id,
                            "client_id": binding.client_id,
                            "as_of_date": request.as_of_date.isoformat(),
                            "integration_status": "not_ingested",
                        }
                    )
                ),
            ),
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

        missing_data_families = ["external_eligible_hedge_instrument"]
        blocked_capabilities = [
            "eligible_hedge_instrument_selection",
            "hedge_instrument_suitability",
            "product_recommendation",
            "counterparty_selection",
            "treasury_instruction",
            "order_generation",
            "best_execution",
            "oms_acknowledgement",
            "fills",
            "settlement",
            "autonomous_treasury_action",
        ]

        return ExternalEligibleHedgeInstrumentResponse(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            mandate_id=binding.mandate_id,
            reporting_currency=request.reporting_currency,
            exposure_currencies=request.exposure_currencies,
            instrument_types=request.instrument_types,
            eligible_instruments=[],
            supportability=ExternalEligibleHedgeInstrumentSupportability(
                instrument_count=0,
                missing_data_families=missing_data_families,
                blocked_capabilities=blocked_capabilities,
            ),
            lineage={
                "source_system": "external-bank-treasury",
                "source_table": "not_ingested",
                "contract_version": "rfc_039_external_eligible_hedge_instrument_v1",
                "integration_status": "not_ingested",
                "runtime_posture": "fail_closed",
                "non_claims": ",".join(blocked_capabilities),
            },
            **source_data_product_runtime_metadata(
                as_of_date=request.as_of_date,
                tenant_id=request.tenant_id,
                data_quality_status="MISSING",
                latest_evidence_timestamp=None,
                source_batch_fingerprint=build_request_fingerprint(
                    {
                        "product": "ExternalEligibleHedgeInstrument",
                        "portfolio_id": portfolio_id,
                        "client_id": binding.client_id,
                        "mandate_id": binding.mandate_id,
                        "as_of_date": request.as_of_date.isoformat(),
                        "reporting_currency": request.reporting_currency,
                        "exposure_currencies": sorted(request.exposure_currencies),
                        "instrument_types": sorted(request.instrument_types),
                        "integration_status": "not_ingested",
                    }
                ),
                snapshot_id=(
                    "external_eligible_hedge_instrument:"
                    + build_request_fingerprint(
                        {
                            "portfolio_id": portfolio_id,
                            "client_id": binding.client_id,
                            "as_of_date": request.as_of_date.isoformat(),
                            "integration_status": "not_ingested",
                        }
                    )
                ),
            ),
        )

    async def get_external_fx_forward_curve(
        self,
        request: ExternalFXForwardCurveRequest,
    ) -> ExternalFXForwardCurveResponse:
        missing_data_families = ["external_fx_forward_curve"]
        blocked_capabilities = [
            "forward_pricing",
            "fx_valuation_methodology",
            "hedge_advice",
            "treasury_instruction",
            "counterparty_selection",
            "order_generation",
            "best_execution",
            "venue_routing",
            "oms_acknowledgement",
            "fills",
            "settlement",
            "autonomous_treasury_action",
        ]

        return ExternalFXForwardCurveResponse(
            reporting_currency=request.reporting_currency,
            currency_pairs=request.currency_pairs,
            tenors=request.tenors,
            curve_points=[],
            supportability=ExternalFXForwardCurveSupportability(
                curve_point_count=0,
                missing_data_families=missing_data_families,
                blocked_capabilities=blocked_capabilities,
            ),
            lineage={
                "source_system": "external-bank-treasury",
                "source_table": "not_ingested",
                "contract_version": "rfc_039_external_fx_forward_curve_v1",
                "integration_status": "not_ingested",
                "runtime_posture": "fail_closed",
                "non_claims": ",".join(blocked_capabilities),
            },
            **source_data_product_runtime_metadata(
                as_of_date=request.as_of_date,
                tenant_id=request.tenant_id,
                data_quality_status="MISSING",
                latest_evidence_timestamp=None,
                source_batch_fingerprint=build_request_fingerprint(
                    {
                        "product": "ExternalFXForwardCurve",
                        "as_of_date": request.as_of_date.isoformat(),
                        "reporting_currency": request.reporting_currency,
                        "currency_pairs": sorted(request.currency_pairs),
                        "tenors": sorted(request.tenors),
                        "integration_status": "not_ingested",
                    }
                ),
                snapshot_id=(
                    "external_fx_forward_curve:"
                    + build_request_fingerprint(
                        {
                            "as_of_date": request.as_of_date.isoformat(),
                            "currency_pairs": sorted(request.currency_pairs),
                            "tenors": sorted(request.tenors),
                            "integration_status": "not_ingested",
                        }
                    )
                ),
            ),
        )

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

        request_scope_fingerprint = build_request_fingerprint(
            {
                "portfolio_id": portfolio_id,
                "as_of_date": request.as_of_date.isoformat(),
                "security_ids": sorted(request.security_ids or []),
                "lot_status_filter": request.lot_status_filter,
                "include_closed_lots": request.include_closed_lots,
                "tenant_id": request.tenant_id,
            }
        )
        cursor = self._decode_page_token(request.page.page_token)
        token_scope = cursor.get("scope_fingerprint")
        if token_scope and token_scope != request_scope_fingerprint:
            raise ValueError("Portfolio tax-lot page token does not match request scope.")

        rows = await self._buy_state_repository.list_portfolio_tax_lots(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            security_ids=request.security_ids,
            include_closed_lots=request.include_closed_lots,
            lot_status_filter=request.lot_status_filter,
            after_sort_key=portfolio_tax_lot_after_sort_key(cursor),
            limit=request.page.page_size + 1,
        )
        has_more = len(rows) > request.page.page_size
        page_rows = rows[: request.page.page_size]

        next_page_token: str | None = None
        if has_more and page_rows:
            last_lot = page_rows[-1][0]
            next_page_token = self._encode_page_token(
                {
                    "scope_fingerprint": request_scope_fingerprint,
                    "last_acquisition_date": last_lot.acquisition_date.isoformat(),
                    "last_lot_id": last_lot.lot_id,
                }
            )

        return build_portfolio_tax_lot_window_response(
            portfolio_id=portfolio_id,
            request=request,
            request_scope_fingerprint=request_scope_fingerprint,
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

        request_scope_fingerprint = build_request_fingerprint(
            {
                "portfolio_id": portfolio_id,
                "as_of_date": request.as_of_date.isoformat(),
                "window": {
                    "start_date": request.window.start_date.isoformat(),
                    "end_date": request.window.end_date.isoformat(),
                },
                "security_ids": sorted(request.security_ids or []),
                "transaction_types": sorted(request.transaction_types or []),
                "min_observation_count": request.min_observation_count,
                "tenant_id": request.tenant_id,
            }
        )
        cursor = self._decode_page_token(request.page.page_token)
        token_scope = cursor.get("scope_fingerprint")
        if token_scope and token_scope != request_scope_fingerprint:
            raise ValueError("Transaction cost curve page token does not match request scope.")
        after_key = tuple(cursor.get("last_curve_key") or ())

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
            after_key=after_key,
            page_size=request.page.page_size,
        )

        next_page_token: str | None = None
        if curve_page.has_more and curve_page.points:
            last_point = curve_page.points[-1]
            next_page_token = self._encode_page_token(
                {
                    "scope_fingerprint": request_scope_fingerprint,
                    "last_curve_key": [
                        last_point.security_id,
                        last_point.transaction_type,
                        last_point.currency,
                    ],
                }
            )

        return build_transaction_cost_curve_response(
            portfolio_id=portfolio_id,
            request=request,
            request_scope_fingerprint=request_scope_fingerprint,
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
        resolved_mandate_id: str | None = request.mandate_id
        resolved_model_portfolio_id: str | None = request.model_portfolio_id

        mandate_response: DiscretionaryMandateBindingResponse | None = None
        try:
            mandate_response = await self.resolve_discretionary_mandate_binding(
                portfolio_id,
                DiscretionaryMandateBindingRequest(
                    as_of_date=request.as_of_date,
                    tenant_id=request.tenant_id,
                    mandate_id=request.mandate_id,
                    include_policy_pack=True,
                ),
            )
        except (LookupError, ValueError):
            mandate_response = None
        if mandate_response is None:
            families.append(
                unavailable_dpm_source_family(
                    family="mandate",
                    product_name="DiscretionaryMandateBinding",
                    reason="MANDATE_BINDING_UNAVAILABLE",
                    missing_items=["mandate_binding"],
                )
            )
        else:
            resolved_mandate_id = mandate_response.mandate_id
            resolved_model_portfolio_id = (
                resolved_model_portfolio_id or mandate_response.model_portfolio_id
            )
            families.append(
                dpm_source_family_readiness(
                    family="mandate",
                    product_name="DiscretionaryMandateBinding",
                    state=mandate_response.supportability.state,
                    reason=mandate_response.supportability.reason,
                    missing_items=mandate_response.supportability.missing_data_families,
                    evidence_count=1,
                )
            )

        target_instrument_ids: list[str] = []
        if resolved_model_portfolio_id is None:
            families.append(
                unavailable_dpm_source_family(
                    family="model_targets",
                    product_name="DpmModelPortfolioTarget",
                    reason="MODEL_PORTFOLIO_ID_UNAVAILABLE",
                    missing_items=["model_portfolio_id"],
                )
            )
        else:
            try:
                model_response = await self.resolve_model_portfolio_targets(
                    resolved_model_portfolio_id,
                    ModelPortfolioTargetRequest(
                        as_of_date=request.as_of_date,
                        include_inactive_targets=False,
                        tenant_id=request.tenant_id,
                    ),
                )
            except (LookupError, ValueError):
                model_response = None
            if model_response is None:
                families.append(
                    unavailable_dpm_source_family(
                        family="model_targets",
                        product_name="DpmModelPortfolioTarget",
                        reason="MODEL_TARGETS_UNAVAILABLE",
                        missing_items=[resolved_model_portfolio_id],
                    )
                )
            else:
                target_instrument_ids = [target.instrument_id for target in model_response.targets]
                families.append(
                    dpm_source_family_readiness(
                        family="model_targets",
                        product_name="DpmModelPortfolioTarget",
                        state=model_response.supportability.state,
                        reason=model_response.supportability.reason,
                        evidence_count=model_response.supportability.target_count,
                    )
                )

        evaluated_instrument_ids = sorted({*request.instrument_ids, *target_instrument_ids})
        if evaluated_instrument_ids:
            try:
                eligibility = await self.resolve_instrument_eligibility_bulk(
                    InstrumentEligibilityBulkRequest(
                        as_of_date=request.as_of_date,
                        security_ids=evaluated_instrument_ids,
                        tenant_id=request.tenant_id,
                        include_restricted_rationale=False,
                    )
                )
                families.append(
                    dpm_source_family_readiness(
                        family="eligibility",
                        product_name="InstrumentEligibilityProfile",
                        state=eligibility.supportability.state,
                        reason=eligibility.supportability.reason,
                        missing_items=eligibility.supportability.missing_security_ids,
                        evidence_count=eligibility.supportability.resolved_count,
                    )
                )
            except (LookupError, ValueError):
                families.append(
                    unavailable_dpm_source_family(
                        family="eligibility",
                        product_name="InstrumentEligibilityProfile",
                        reason="INSTRUMENT_ELIGIBILITY_UNAVAILABLE",
                        missing_items=evaluated_instrument_ids[:10],
                    )
                )
        else:
            families.append(
                unavailable_dpm_source_family(
                    family="eligibility",
                    product_name="InstrumentEligibilityProfile",
                    reason="DPM_INSTRUMENT_UNIVERSE_EMPTY",
                    missing_items=["instrument_ids"],
                )
            )

        try:
            tax_lots = await self.get_portfolio_tax_lot_window(
                portfolio_id=portfolio_id,
                request=PortfolioTaxLotWindowRequest(
                    as_of_date=request.as_of_date,
                    security_ids=evaluated_instrument_ids or None,
                    tenant_id=request.tenant_id,
                ),
            )
            families.append(
                dpm_source_family_readiness(
                    family="tax_lots",
                    product_name="PortfolioTaxLotWindow",
                    state=tax_lots.supportability.state,
                    reason=tax_lots.supportability.reason,
                    missing_items=tax_lots.supportability.missing_security_ids,
                    evidence_count=tax_lots.supportability.returned_lot_count,
                )
            )
        except (LookupError, ValueError):
            families.append(
                unavailable_dpm_source_family(
                    family="tax_lots",
                    product_name="PortfolioTaxLotWindow",
                    reason="PORTFOLIO_TAX_LOTS_UNAVAILABLE",
                    missing_items=[portfolio_id],
                )
            )

        try:
            market_data = await self.get_market_data_coverage(
                MarketDataCoverageRequest(
                    as_of_date=request.as_of_date,
                    instrument_ids=evaluated_instrument_ids,
                    currency_pairs=request.currency_pairs,
                    valuation_currency=request.valuation_currency,
                    max_staleness_days=request.max_staleness_days,
                    tenant_id=request.tenant_id,
                )
            )
            families.append(
                dpm_source_family_readiness(
                    family="market_data",
                    product_name="MarketDataCoverageWindow",
                    state=market_data.supportability.state,
                    reason=market_data.supportability.reason,
                    missing_items=[
                        *market_data.supportability.missing_instrument_ids,
                        *market_data.supportability.missing_currency_pairs,
                    ],
                    stale_items=[
                        *market_data.supportability.stale_instrument_ids,
                        *market_data.supportability.stale_currency_pairs,
                    ],
                    evidence_count=(
                        market_data.supportability.resolved_price_count
                        + market_data.supportability.resolved_fx_count
                    ),
                )
            )
        except (LookupError, ValueError):
            families.append(
                unavailable_dpm_source_family(
                    family="market_data",
                    product_name="MarketDataCoverageWindow",
                    reason="MARKET_DATA_COVERAGE_UNAVAILABLE",
                    missing_items=["market_data_coverage"],
                )
            )

        return build_dpm_source_readiness_response(
            portfolio_id=portfolio_id,
            request=request,
            resolved_mandate_id=resolved_mandate_id,
            resolved_model_portfolio_id=resolved_model_portfolio_id,
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
        records: list[BenchmarkDefinitionResponse] = []
        for row in rows:
            components = components_by_benchmark.get(row.benchmark_id, [])
            records.append(benchmark_definition_response(row, components=components))
        return BenchmarkCatalogResponse(as_of_date=as_of_date, records=records)

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
        return IndexCatalogResponse(
            as_of_date=as_of_date,
            records=[index_definition_response(row) for row in rows],
        )

    async def get_benchmark_market_series(
        self,
        benchmark_id: str,
        request: BenchmarkMarketSeriesRequest,
    ) -> BenchmarkMarketSeriesResponse:
        requested_fields = set(request.series_fields)
        definition = await self._reference_repository.get_benchmark_definition(
            benchmark_id, request.as_of_date
        )
        benchmark_currency = (
            definition.benchmark_currency if definition else (request.target_currency or "UNKNOWN")
        )
        request_scope_fingerprint = build_request_fingerprint(
            {
                "benchmark_id": benchmark_id,
                "as_of_date": request.as_of_date.isoformat(),
                "window": {
                    "start_date": request.window.start_date.isoformat(),
                    "end_date": request.window.end_date.isoformat(),
                },
                "frequency": request.frequency,
                "target_currency": request.target_currency,
                "series_fields": sorted(request.series_fields),
            }
        )
        page = getattr(request, "page", None)
        page_size = getattr(page, "page_size", 250)
        page_token = getattr(page, "page_token", None)
        cursor = self._decode_page_token(page_token)
        token_scope = cursor.get("scope_fingerprint")
        if token_scope and token_scope != request_scope_fingerprint:
            raise ValueError("Benchmark market series page token does not match request scope.")
        cursor_index_id = cursor.get("last_index_id")
        candidate_index_ids = (
            await self._reference_repository.list_benchmark_component_index_ids_overlapping_window(
                benchmark_id=benchmark_id,
                start_date=request.window.start_date,
                end_date=request.window.end_date,
                after_index_id=cursor_index_id,
                limit=page_size + 1,
            )
        )
        has_more = len(candidate_index_ids) > page_size
        index_ids = candidate_index_ids[:page_size]
        fx_context = benchmark_market_series_fx_context(
            benchmark_currency=benchmark_currency,
            target_currency=request.target_currency,
            requested_fields=requested_fields,
        )
        market_read_names = ["components"]
        market_reads: list[Any] = [
            self._reference_repository.list_benchmark_components_overlapping_window(
                benchmark_id=benchmark_id,
                start_date=request.window.start_date,
                end_date=request.window.end_date,
                index_ids=index_ids,
            )
        ]
        if "index_price" in requested_fields:
            market_read_names.append("index_prices")
            market_reads.append(
                self._reference_repository.list_index_price_points(
                    index_ids=index_ids,
                    start_date=request.window.start_date,
                    end_date=request.window.end_date,
                )
            )
        if "index_return" in requested_fields:
            market_read_names.append("index_returns")
            market_reads.append(
                self._reference_repository.list_index_return_points(
                    index_ids=index_ids,
                    start_date=request.window.start_date,
                    end_date=request.window.end_date,
                )
            )
        if "benchmark_return" in requested_fields:
            market_read_names.append("benchmark_returns")
            market_reads.append(
                self._reference_repository.list_benchmark_return_points(
                    benchmark_id=benchmark_id,
                    start_date=request.window.start_date,
                    end_date=request.window.end_date,
                )
            )

        if fx_context.should_read_fx_rates:
            market_read_names.append("fx_rates")
            market_reads.append(
                self._reference_repository.get_fx_rates(
                    from_currency=benchmark_currency,
                    to_currency=request.target_currency,
                    start_date=request.window.start_date,
                    end_date=request.window.end_date,
                )
            )

        market_results = {}
        for name, market_read in zip(market_read_names, market_reads, strict=True):
            market_results[name] = await market_read
        next_page_token: str | None = None
        if has_more and index_ids:
            next_page_token = self._encode_page_token(
                {
                    "scope_fingerprint": request_scope_fingerprint,
                    "last_index_id": index_ids[-1],
                }
            )

        return build_benchmark_market_series_response(
            benchmark_id=benchmark_id,
            request=request,
            benchmark_currency=benchmark_currency,
            request_scope_fingerprint=request_scope_fingerprint,
            page_size=page_size,
            has_more=has_more,
            next_page_token=next_page_token,
            index_ids=index_ids,
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
        return IndexPriceSeriesResponse(
            index_id=index_id,
            resolved_window=IntegrationWindow(
                start_date=request.window.start_date,
                end_date=request.window.end_date,
            ),
            frequency=request.frequency,
            points=[index_price_series_point(row) for row in rows],
            lineage={
                "contract_version": "rfc_062_v1",
                "source_system": "lotus-core-query-service",
                "generated_by": "integration.index_price_series",
            },
            **source_product_runtime_metadata(
                getattr(request, "as_of_date", request.window.end_date),
                data_quality_status=market_reference_data_quality_status(
                    rows,
                    required_count=len(rows),
                ),
                latest_evidence_timestamp=latest_reference_evidence_timestamp(rows),
            ),
        )

    async def get_index_return_series(
        self, index_id: str, request: IndexSeriesRequest
    ) -> IndexReturnSeriesResponse:
        request_fingerprint = series_request_fingerprint(
            series_key="index_return_series",
            identifier_key="index_id",
            identifier_value=index_id,
            request=request,
        )
        rows = await self._reference_repository.list_index_return_series(
            index_id=index_id,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        )
        return IndexReturnSeriesResponse(
            index_id=index_id,
            as_of_date=request.as_of_date,
            resolved_window=IntegrationWindow(
                start_date=request.window.start_date,
                end_date=request.window.end_date,
            ),
            frequency=request.frequency,
            request_fingerprint=request_fingerprint,
            points=[index_return_series_point(row) for row in rows],
            lineage={
                "contract_version": "rfc_062_v1",
                "source_system": "lotus-core-query-service",
                "generated_by": "integration.index_return_series",
            },
            **source_product_runtime_metadata_without_as_of_date(
                request.as_of_date,
                data_quality_status=market_reference_data_quality_status(
                    rows,
                    required_count=len(rows),
                ),
                latest_evidence_timestamp=latest_reference_evidence_timestamp(rows),
            ),
        )

    async def get_benchmark_return_series(
        self, benchmark_id: str, request: BenchmarkReturnSeriesRequest
    ) -> BenchmarkReturnSeriesResponse:
        request_fingerprint = series_request_fingerprint(
            series_key="benchmark_return_series",
            identifier_key="benchmark_id",
            identifier_value=benchmark_id,
            request=request,
        )
        rows = await self._reference_repository.list_benchmark_return_points(
            benchmark_id=benchmark_id,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        )
        return BenchmarkReturnSeriesResponse(
            benchmark_id=benchmark_id,
            as_of_date=request.as_of_date,
            resolved_window=IntegrationWindow(
                start_date=request.window.start_date,
                end_date=request.window.end_date,
            ),
            frequency=request.frequency,
            request_fingerprint=request_fingerprint,
            points=[benchmark_return_series_point(row) for row in rows],
            lineage={
                "contract_version": "rfc_062_v1",
                "source_system": "lotus-core-query-service",
                "generated_by": "integration.benchmark_return_series",
            },
        )

    async def get_risk_free_series(self, request: RiskFreeSeriesRequest) -> RiskFreeSeriesResponse:
        normalized_currency = normalize_currency_code(request.currency)
        request_fingerprint = series_request_fingerprint(
            series_key="risk_free_series",
            identifier_key="currency",
            identifier_value=normalized_currency,
            request=request,
            extras={"series_mode": request.series_mode},
        )
        rows = await self._reference_repository.list_risk_free_series(
            currency=normalized_currency,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        )
        return RiskFreeSeriesResponse(
            currency=normalized_currency,
            as_of_date=request.as_of_date,
            series_mode=request.series_mode,
            resolved_window=IntegrationWindow(
                start_date=request.window.start_date,
                end_date=request.window.end_date,
            ),
            frequency=request.frequency,
            request_fingerprint=request_fingerprint,
            points=[risk_free_series_point(row) for row in rows],
            lineage={
                "contract_version": "rfc_062_v1",
                "source_system": "lotus-core-query-service",
                "generated_by": "integration.risk_free_series",
            },
            **source_product_runtime_metadata_without_as_of_date(
                request.as_of_date,
                data_quality_status=market_reference_data_quality_status(
                    rows,
                    required_count=len(rows),
                ),
                latest_evidence_timestamp=latest_reference_evidence_timestamp(rows),
            ),
        )

    async def get_benchmark_coverage(
        self,
        benchmark_id: str,
        start_date: date,
        end_date: date,
    ) -> CoverageResponse:
        request_fingerprint = build_request_fingerprint(
            {
                "coverage_key": "benchmark_coverage",
                "benchmark_id": benchmark_id,
                "window": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                },
            }
        )
        coverage = await self._reference_repository.get_benchmark_coverage(
            benchmark_id=benchmark_id,
            start_date=start_date,
            end_date=end_date,
        )
        return market_reference_coverage_response(
            coverage=coverage,
            start_date=start_date,
            end_date=end_date,
            request_fingerprint=request_fingerprint,
        )

    async def get_risk_free_coverage(
        self,
        currency: str,
        start_date: date,
        end_date: date,
    ) -> CoverageResponse:
        normalized_currency = normalize_currency_code(currency)
        request_fingerprint = build_request_fingerprint(
            {
                "coverage_key": "risk_free_coverage",
                "currency": normalized_currency,
                "window": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                },
            }
        )
        coverage = await self._reference_repository.get_risk_free_coverage(
            currency=normalized_currency,
            start_date=start_date,
            end_date=end_date,
        )
        return market_reference_coverage_response(
            coverage=coverage,
            start_date=start_date,
            end_date=end_date,
            request_fingerprint=request_fingerprint,
        )

    async def get_classification_taxonomy(
        self,
        as_of_date: date,
        taxonomy_scope: str | None = None,
    ) -> ClassificationTaxonomyResponse:
        request_fingerprint = build_request_fingerprint(
            {
                "taxonomy_key": "classification_taxonomy",
                "as_of_date": as_of_date.isoformat(),
                "taxonomy_scope": taxonomy_scope,
            }
        )
        rows = await self._reference_repository.list_taxonomy(
            as_of_date=as_of_date,
            taxonomy_scope=taxonomy_scope,
        )
        return ClassificationTaxonomyResponse(
            as_of_date=as_of_date,
            records=[classification_taxonomy_entry(row) for row in rows],
            request_fingerprint=request_fingerprint,
            **source_product_runtime_metadata_without_as_of_date(
                as_of_date,
                data_quality_status=market_reference_data_quality_status(
                    rows,
                    required_count=len(rows),
                ),
                latest_evidence_timestamp=latest_reference_evidence_timestamp(rows),
            ),
        )
