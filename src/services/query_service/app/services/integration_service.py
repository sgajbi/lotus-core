import logging
from datetime import UTC, date, datetime
from decimal import Decimal
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
    CioModelChangeAffectedCohortSupportability,
    ClassificationTaxonomyResponse,
    ClientIncomeNeedsScheduleRequest,
    ClientIncomeNeedsScheduleResponse,
    ClientIncomeNeedsScheduleSupportability,
    ClientRestrictionProfileRequest,
    ClientRestrictionProfileResponse,
    ClientRestrictionProfileSupportability,
    ClientTaxProfileRequest,
    ClientTaxProfileResponse,
    ClientTaxProfileSupportability,
    ClientTaxRuleSetRequest,
    ClientTaxRuleSetResponse,
    ClientTaxRuleSetSupportability,
    CoverageResponse,
    DiscretionaryMandateBindingRequest,
    DiscretionaryMandateBindingResponse,
    DiscretionaryMandateBindingSupportability,
    DpmPortfolioUniverseCandidateRequest,
    DpmPortfolioUniverseCandidateResponse,
    DpmPortfolioUniverseCandidateSelectionBasis,
    DpmPortfolioUniverseCandidateSupportability,
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
    InstrumentEligibilitySupportability,
    IntegrationWindow,
    LiquidityReserveRequirementRequest,
    LiquidityReserveRequirementResponse,
    LiquidityReserveRequirementSupportability,
    MarketDataCoverageRequest,
    MarketDataCoverageWindowResponse,
    ModelPortfolioSupportability,
    ModelPortfolioTargetRequest,
    ModelPortfolioTargetResponse,
    PlannedWithdrawalScheduleRequest,
    PlannedWithdrawalScheduleResponse,
    PlannedWithdrawalScheduleSupportability,
    PortfolioManagerBookMembershipRequest,
    PortfolioManagerBookMembershipResponse,
    PortfolioManagerBookMembershipSupportability,
    PortfolioTaxLotWindowRequest,
    PortfolioTaxLotWindowResponse,
    PortfolioTaxLotWindowSupportability,
    RebalanceBandContext,
    ReferencePageMetadata,
    RiskFreeSeriesRequest,
    RiskFreeSeriesResponse,
    SustainabilityPreferenceProfileRequest,
    SustainabilityPreferenceProfileResponse,
    SustainabilityPreferenceProfileSupportability,
    TransactionCostCurveRequest,
    TransactionCostCurveResponse,
    TransactionCostCurveSupportability,
)
from ..dtos.source_data_product_identity import source_data_product_runtime_metadata
from ..repositories.buy_state_repository import BuyStateRepository
from ..repositories.currency_codes import normalize_currency_code
from ..repositories.identifier_normalization import normalize_security_id
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
from .dpm_source_readiness import (
    build_dpm_source_readiness_response,
    dpm_source_family_readiness,
    unavailable_dpm_source_family,
)
from .integration_policy import build_effective_policy_response
from .integration_value_normalization import as_optional_decimal, control_code
from .market_data_coverage import (
    build_market_data_coverage_response,
    market_data_coverage_read_scope,
)
from .market_reference_coverage import market_reference_coverage_response
from .page_token_codec import PageTokenCodec
from .reference_data_helpers import (
    latest_reference_evidence_timestamp,
    market_reference_data_quality_status,
)
from .reference_data_mappers import (
    benchmark_definition_response,
    benchmark_return_series_point,
    cio_model_change_affected_mandate,
    classification_taxonomy_entry,
    client_income_needs_schedule_entry,
    client_restriction_profile_entry,
    client_tax_profile_entry,
    client_tax_rule_set_entry,
    dpm_portfolio_universe_candidate,
    index_definition_response,
    index_price_series_point,
    index_return_series_point,
    instrument_eligibility_record,
    liquidity_reserve_requirement_entry,
    missing_instrument_eligibility_record,
    model_portfolio_target_row,
    planned_withdrawal_schedule_entry,
    portfolio_manager_book_member,
    portfolio_tax_lot_record,
    risk_free_series_point,
    sustainability_preference_profile_entry,
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
from .transaction_cost_curve import build_transaction_cost_curve_page

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
        target_rows = [model_portfolio_target_row(row) for row in targets]
        total_weight = sum((row.target_weight for row in target_rows), Decimal("0"))
        supportability_state: Literal["READY", "DEGRADED", "INCOMPLETE", "UNAVAILABLE"] = "READY"
        supportability_reason = "MODEL_TARGETS_READY"
        if not target_rows:
            supportability_state = "INCOMPLETE"
            supportability_reason = "MODEL_TARGETS_EMPTY"
        elif total_weight != Decimal("1.0000000000"):
            supportability_state = "DEGRADED"
            supportability_reason = "MODEL_TARGET_WEIGHTS_NOT_ONE"

        latest_evidence_timestamp = latest_reference_evidence_timestamp(
            [definition],
            targets,
        )
        return ModelPortfolioTargetResponse(
            model_portfolio_id=definition.model_portfolio_id,
            model_portfolio_version=definition.model_portfolio_version,
            display_name=definition.display_name,
            base_currency=definition.base_currency,
            risk_profile=definition.risk_profile,
            mandate_type=definition.mandate_type,
            rebalance_frequency=definition.rebalance_frequency,
            approval_status=definition.approval_status,
            approved_at=definition.approved_at,
            effective_from=definition.effective_from,
            effective_to=definition.effective_to,
            targets=target_rows,
            supportability=ModelPortfolioSupportability(
                state=supportability_state,
                reason=supportability_reason,
                target_count=len(target_rows),
                total_target_weight=total_weight,
            ),
            lineage={
                "source_system": definition.source_system or "unknown",
                "source_record_id": definition.source_record_id or "unknown",
                "contract_version": "rfc_087_v1",
            },
            **source_product_runtime_metadata(
                request.as_of_date,
                data_quality_status=market_reference_data_quality_status(
                    targets,
                    required_count=len(target_rows),
                ),
                latest_evidence_timestamp=latest_evidence_timestamp,
            ),
        )

    async def resolve_portfolio_manager_book_membership(
        self,
        portfolio_manager_id: str,
        request: PortfolioManagerBookMembershipRequest,
    ) -> PortfolioManagerBookMembershipResponse:
        portfolio_types = [
            portfolio_type.strip().upper()
            for portfolio_type in request.portfolio_types
            if portfolio_type.strip()
        ]
        rows = await self._portfolio_repository.list_portfolio_manager_book_members(
            portfolio_manager_id=portfolio_manager_id,
            as_of_date=request.as_of_date,
            booking_center_code=request.booking_center_code,
            portfolio_types=portfolio_types,
            include_inactive=request.include_inactive,
        )
        members = [portfolio_manager_book_member(row) for row in rows]
        filters_applied = ["portfolio_manager_id", "as_of_date"]
        if request.booking_center_code:
            filters_applied.append("booking_center_code")
        if portfolio_types:
            filters_applied.append("portfolio_types")
        if not request.include_inactive:
            filters_applied.extend(["active_lifecycle_window", "active_status"])

        supportability_state: Literal["READY", "INCOMPLETE"] = "READY"
        supportability_reason = "PM_BOOK_MEMBERSHIP_READY"
        if not members:
            supportability_state = "INCOMPLETE"
            supportability_reason = "PM_BOOK_MEMBERSHIP_EMPTY"

        snapshot_id = build_request_fingerprint(
            {
                "product_name": "PortfolioManagerBookMembership",
                "portfolio_manager_id": portfolio_manager_id,
                "as_of_date": request.as_of_date.isoformat(),
                "booking_center_code": request.booking_center_code,
                "portfolio_types": portfolio_types,
                "include_inactive": request.include_inactive,
                "portfolio_ids": [member.portfolio_id for member in members],
            }
        )
        latest_evidence_timestamp = latest_reference_evidence_timestamp(rows)

        return PortfolioManagerBookMembershipResponse(
            portfolio_manager_id=portfolio_manager_id,
            booking_center_code=request.booking_center_code,
            members=members,
            supportability=PortfolioManagerBookMembershipSupportability(
                state=supportability_state,
                reason=supportability_reason,
                returned_portfolio_count=len(members),
                filters_applied=filters_applied,
            ),
            lineage={
                "source_system": "lotus-core",
                "source_table": "portfolios",
                "source_field": "advisor_id",
                "contract_version": "rfc_041_pm_book_membership_v1",
            },
            **source_data_product_runtime_metadata(
                as_of_date=request.as_of_date,
                data_quality_status="ACCEPTED" if members else "MISSING",
                latest_evidence_timestamp=latest_evidence_timestamp,
                snapshot_id=f"pm_book_membership:{snapshot_id}",
            ),
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
        affected_mandates = [cio_model_change_affected_mandate(row) for row in rows]
        filters_applied = ["model_portfolio_id", "as_of_date"]
        if request.booking_center_code:
            filters_applied.append("booking_center_code")
        if not request.include_inactive_mandates:
            filters_applied.append("active_discretionary_authority")

        supportability_state: Literal["READY", "INCOMPLETE"] = "READY"
        supportability_reason = "CIO_MODEL_CHANGE_COHORT_READY"
        if not affected_mandates:
            supportability_state = "INCOMPLETE"
            supportability_reason = "CIO_MODEL_CHANGE_COHORT_EMPTY"

        snapshot_fingerprint = build_request_fingerprint(
            {
                "product_name": "CioModelChangeAffectedCohort",
                "model_portfolio_id": model_portfolio_id,
                "model_portfolio_version": definition.model_portfolio_version,
                "as_of_date": request.as_of_date.isoformat(),
                "booking_center_code": request.booking_center_code,
                "include_inactive_mandates": request.include_inactive_mandates,
                "mandate_ids": [mandate.mandate_id for mandate in affected_mandates],
                "portfolio_ids": [mandate.portfolio_id for mandate in affected_mandates],
            }
        )
        event_id = (
            "cio_model_change:"
            f"{model_portfolio_id}:"
            f"{definition.model_portfolio_version}:"
            f"{request.as_of_date.isoformat()}:{snapshot_fingerprint}"
        )
        latest_evidence_timestamp = latest_reference_evidence_timestamp(
            [definition],
            rows,
        )

        return CioModelChangeAffectedCohortResponse(
            model_portfolio_id=definition.model_portfolio_id,
            model_portfolio_version=definition.model_portfolio_version,
            model_change_event_id=event_id,
            approval_state=definition.approval_status,
            approved_at=definition.approved_at,
            effective_from=definition.effective_from,
            effective_to=definition.effective_to,
            affected_mandates=affected_mandates,
            supportability=CioModelChangeAffectedCohortSupportability(
                state=supportability_state,
                reason=supportability_reason,
                returned_mandate_count=len(affected_mandates),
                filters_applied=filters_applied,
            ),
            lineage={
                "source_system": definition.source_system or "lotus-core",
                "model_definition_source_record_id": definition.source_record_id or "unknown",
                "mandate_binding_table": "portfolio_mandate_bindings",
                "contract_version": "rfc_041_cio_model_change_cohort_v1",
            },
            **source_data_product_runtime_metadata(
                as_of_date=request.as_of_date,
                tenant_id=request.tenant_id,
                data_quality_status="ACCEPTED" if affected_mandates else "MISSING",
                latest_evidence_timestamp=latest_evidence_timestamp,
                source_batch_fingerprint=snapshot_fingerprint,
                snapshot_id=f"cio_model_change_cohort:{snapshot_fingerprint}",
            ),
        )

    async def resolve_dpm_portfolio_universe_candidates(
        self,
        request: DpmPortfolioUniverseCandidateRequest,
    ) -> DpmPortfolioUniverseCandidateResponse:
        booking_center_code = (
            request.booking_center_code.strip() if request.booking_center_code else None
        )
        if booking_center_code == "":
            booking_center_code = None
        model_portfolio_ids = sorted(
            {
                model_portfolio_id.strip()
                for model_portfolio_id in request.model_portfolio_ids
                if model_portfolio_id.strip()
            }
        )
        request_scope_fingerprint = build_request_fingerprint(
            {
                "product_name": "DpmPortfolioUniverseCandidate",
                "as_of_date": request.as_of_date.isoformat(),
                "booking_center_code": booking_center_code,
                "model_portfolio_ids": model_portfolio_ids,
                "include_inactive_mandates": request.include_inactive_mandates,
                "tenant_id": request.tenant_id,
            }
        )
        cursor = self._decode_page_token(request.page.page_token)
        token_scope = cursor.get("scope_fingerprint")
        if token_scope and token_scope != request_scope_fingerprint:
            raise ValueError("DPM portfolio-universe page token does not match request scope.")

        after_sort_key: tuple[str, str] | None = None
        if cursor.get("last_portfolio_id") and cursor.get("last_mandate_id"):
            after_sort_key = (str(cursor["last_portfolio_id"]), str(cursor["last_mandate_id"]))

        rows = await self._reference_repository.list_dpm_portfolio_universe_candidates(
            as_of_date=request.as_of_date,
            booking_center_code=booking_center_code,
            model_portfolio_ids=model_portfolio_ids,
            include_inactive_mandates=request.include_inactive_mandates,
            after_sort_key=after_sort_key,
            limit=request.page.page_size + 1,
        )
        has_more = len(rows) > request.page.page_size
        page_rows = rows[: request.page.page_size]
        candidates = [dpm_portfolio_universe_candidate(row) for row in page_rows]

        next_page_token: str | None = None
        if has_more and candidates:
            last_candidate = candidates[-1]
            next_page_token = self._encode_page_token(
                {
                    "scope_fingerprint": request_scope_fingerprint,
                    "last_portfolio_id": last_candidate.portfolio_id,
                    "last_mandate_id": last_candidate.mandate_id,
                }
            )

        filters_applied = ["as_of_date"]
        if booking_center_code:
            filters_applied.append("booking_center_code")
        if model_portfolio_ids:
            filters_applied.append("model_portfolio_ids")
        if not request.include_inactive_mandates:
            filters_applied.append("active_discretionary_authority")

        supportability_state: Literal["READY", "DEGRADED", "INCOMPLETE"] = "READY"
        supportability_reason = "DPM_PORTFOLIO_UNIVERSE_READY"
        data_quality_status = "ACCEPTED"
        if not candidates:
            supportability_state = "INCOMPLETE"
            supportability_reason = "DPM_PORTFOLIO_UNIVERSE_EMPTY"
            data_quality_status = "MISSING"
        elif has_more:
            supportability_state = "DEGRADED"
            supportability_reason = "DPM_PORTFOLIO_UNIVERSE_PAGE_PARTIAL"
            data_quality_status = "PARTIAL"

        return DpmPortfolioUniverseCandidateResponse(
            candidates=candidates,
            page=ReferencePageMetadata(
                page_size=request.page.page_size,
                sort_key="portfolio_id:asc,mandate_id:asc",
                returned_component_count=len(candidates),
                request_scope_fingerprint=request_scope_fingerprint,
                next_page_token=next_page_token,
            ),
            supportability=DpmPortfolioUniverseCandidateSupportability(
                state=supportability_state,
                reason=supportability_reason,
                returned_candidate_count=len(candidates),
                filters_applied=filters_applied,
                page_truncated=has_more,
            ),
            selection_basis=DpmPortfolioUniverseCandidateSelectionBasis(
                basis_type="EFFECTIVE_DISCRETIONARY_MANDATE_BINDING",
                source_table="portfolio_mandate_bindings",
                included_when=[
                    "mandate_type=discretionary",
                    "effective_from<=as_of_date",
                    "effective_to is null or effective_to>=as_of_date",
                    "active authority unless include_inactive_mandates=true",
                ],
                downstream_boundary=(
                    "Candidate membership is not relationship householding, suitability approval, "
                    "portfolio-manager ranking, execution readiness, client communication "
                    "workflow, or external workflow ownership."
                ),
            ),
            lineage={
                "source_system": "lotus-core",
                "source_table": "portfolio_mandate_bindings",
                "source_filter": "mandate_type=discretionary",
                "contract_version": "rfc_037_dpm_portfolio_universe_candidate_v1",
            },
            **source_data_product_runtime_metadata(
                as_of_date=request.as_of_date,
                tenant_id=request.tenant_id,
                data_quality_status=data_quality_status,
                latest_evidence_timestamp=latest_reference_evidence_timestamp(page_rows),
                source_batch_fingerprint=request_scope_fingerprint,
                snapshot_id=f"dpm_portfolio_universe:{request_scope_fingerprint}",
            ),
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

        missing_data_families: list[str] = []
        supportability_state: Literal["READY", "DEGRADED", "INCOMPLETE", "UNAVAILABLE"] = "READY"
        supportability_reason = "MANDATE_BINDING_READY"
        discretionary_authority_status = control_code(row.discretionary_authority_status)
        if discretionary_authority_status != "ACTIVE":
            supportability_state = "INCOMPLETE"
            supportability_reason = "DISCRETIONARY_AUTHORITY_NOT_ACTIVE"
            missing_data_families.append("active_discretionary_authority")
        if request.include_policy_pack and not row.policy_pack_id:
            supportability_state = "INCOMPLETE"
            supportability_reason = "MANDATE_POLICY_PACK_MISSING"
            missing_data_families.append("policy_pack")
        mandate_objective = getattr(row, "mandate_objective", None)
        review_cadence = getattr(row, "review_cadence", None)
        last_review_date = getattr(row, "last_review_date", None)
        next_review_due_date = getattr(row, "next_review_due_date", None)
        if not mandate_objective:
            if supportability_state == "READY":
                supportability_state = "INCOMPLETE"
                supportability_reason = "MANDATE_OBJECTIVE_MISSING"
            missing_data_families.append("mandate_objective")
        if not review_cadence or last_review_date is None or next_review_due_date is None:
            if supportability_state == "READY":
                supportability_state = "INCOMPLETE"
                supportability_reason = "MANDATE_REVIEW_SCHEDULE_MISSING"
            missing_data_families.append("mandate_review_schedule")
        elif next_review_due_date < request.as_of_date and supportability_state == "READY":
            supportability_state = "DEGRADED"
            supportability_reason = "MANDATE_REVIEW_OVERDUE"

        bands = dict(row.rebalance_bands or {})
        default_band = as_optional_decimal(bands.get("default_band")) or Decimal("0")
        cash_reserve_raw = bands.get("cash_reserve_weight")

        return DiscretionaryMandateBindingResponse(
            portfolio_id=row.portfolio_id,
            mandate_id=row.mandate_id,
            client_id=row.client_id,
            mandate_type=row.mandate_type,
            discretionary_authority_status=discretionary_authority_status,
            booking_center_code=row.booking_center_code,
            jurisdiction_code=row.jurisdiction_code,
            model_portfolio_id=row.model_portfolio_id,
            policy_pack_id=row.policy_pack_id if request.include_policy_pack else None,
            mandate_objective=mandate_objective,
            risk_profile=row.risk_profile,
            investment_horizon=row.investment_horizon,
            review_cadence=review_cadence,
            last_review_date=last_review_date,
            next_review_due_date=next_review_due_date,
            leverage_allowed=bool(row.leverage_allowed),
            tax_awareness_allowed=bool(row.tax_awareness_allowed),
            settlement_awareness_required=bool(row.settlement_awareness_required),
            rebalance_frequency=row.rebalance_frequency,
            rebalance_bands=RebalanceBandContext(
                default_band=default_band,
                cash_reserve_weight=as_optional_decimal(cash_reserve_raw),
            ),
            effective_from=row.effective_from,
            effective_to=row.effective_to,
            binding_version=int(row.binding_version),
            supportability=DiscretionaryMandateBindingSupportability(
                state=supportability_state,
                reason=supportability_reason,
                missing_data_families=missing_data_families,
            ),
            lineage={
                "source_system": row.source_system or "unknown",
                "source_record_id": row.source_record_id or "unknown",
                "contract_version": "rfc_087_v1",
            },
            **source_product_runtime_metadata(
                request.as_of_date,
                data_quality_status=control_code(row.quality_status, default="UNKNOWN"),
                latest_evidence_timestamp=latest_reference_evidence_timestamp([row]),
            ),
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
        entries = [client_restriction_profile_entry(row) for row in rows]
        supportability_state: Literal["READY", "INCOMPLETE", "UNAVAILABLE"] = "READY"
        supportability_reason = "CLIENT_RESTRICTION_PROFILE_READY"
        missing_data_families: list[str] = []
        if not rows:
            supportability_state = "INCOMPLETE"
            supportability_reason = "CLIENT_RESTRICTION_PROFILE_EMPTY"
            missing_data_families.append("client_restrictions")

        latest_evidence_timestamp = latest_reference_evidence_timestamp([binding], rows)
        return ClientRestrictionProfileResponse(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            mandate_id=binding.mandate_id,
            restrictions=entries,
            supportability=ClientRestrictionProfileSupportability(
                state=supportability_state,
                reason=supportability_reason,
                restriction_count=len(entries),
                missing_data_families=missing_data_families,
            ),
            lineage={
                "source_system": "lotus-core-query-service",
                "source_table": "client_restriction_profiles,portfolio_mandate_bindings",
                "contract_version": "rfc_040_client_restriction_profile_v1",
            },
            **source_data_product_runtime_metadata(
                as_of_date=request.as_of_date,
                tenant_id=request.tenant_id,
                data_quality_status=("ACCEPTED" if rows else "MISSING"),
                latest_evidence_timestamp=latest_evidence_timestamp,
                source_batch_fingerprint=build_request_fingerprint(
                    {
                        "product": "ClientRestrictionProfile",
                        "portfolio_id": portfolio_id,
                        "client_id": binding.client_id,
                        "mandate_id": binding.mandate_id,
                        "as_of_date": request.as_of_date.isoformat(),
                        "row_count": len(rows),
                    }
                ),
                snapshot_id=(
                    "client_restriction_profile:"
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
        entries = [sustainability_preference_profile_entry(row) for row in rows]
        supportability_state: Literal["READY", "INCOMPLETE", "UNAVAILABLE"] = "READY"
        supportability_reason = "SUSTAINABILITY_PREFERENCE_PROFILE_READY"
        missing_data_families: list[str] = []
        if not rows:
            supportability_state = "INCOMPLETE"
            supportability_reason = "SUSTAINABILITY_PREFERENCE_PROFILE_EMPTY"
            missing_data_families.append("sustainability_preferences")

        latest_evidence_timestamp = latest_reference_evidence_timestamp([binding], rows)
        return SustainabilityPreferenceProfileResponse(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            mandate_id=binding.mandate_id,
            preferences=entries,
            supportability=SustainabilityPreferenceProfileSupportability(
                state=supportability_state,
                reason=supportability_reason,
                preference_count=len(entries),
                missing_data_families=missing_data_families,
            ),
            lineage={
                "source_system": "lotus-core-query-service",
                "source_table": "sustainability_preference_profiles,portfolio_mandate_bindings",
                "contract_version": "rfc_040_sustainability_preference_profile_v1",
            },
            **source_data_product_runtime_metadata(
                as_of_date=request.as_of_date,
                tenant_id=request.tenant_id,
                data_quality_status=("ACCEPTED" if rows else "MISSING"),
                latest_evidence_timestamp=latest_evidence_timestamp,
                source_batch_fingerprint=build_request_fingerprint(
                    {
                        "product": "SustainabilityPreferenceProfile",
                        "portfolio_id": portfolio_id,
                        "client_id": binding.client_id,
                        "mandate_id": binding.mandate_id,
                        "as_of_date": request.as_of_date.isoformat(),
                        "row_count": len(rows),
                    }
                ),
                snapshot_id=(
                    "sustainability_preference_profile:"
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
        rows_by_security_id = {normalize_security_id(row.security_id): row for row in rows}

        records = []
        missing_security_ids: list[str] = []
        for requested_security_id in request.security_ids:
            security_id = normalize_security_id(requested_security_id)
            row = rows_by_security_id.get(security_id)
            if row is None:
                missing_security_ids.append(security_id)
                records.append(missing_instrument_eligibility_record(security_id))
                continue
            records.append(instrument_eligibility_record(row))

        supportability_state: Literal["READY", "DEGRADED", "INCOMPLETE", "UNAVAILABLE"] = "READY"
        supportability_reason = "INSTRUMENT_ELIGIBILITY_READY"
        if missing_security_ids:
            supportability_state = "INCOMPLETE"
            supportability_reason = "INSTRUMENT_ELIGIBILITY_MISSING"

        return InstrumentEligibilityBulkResponse(
            records=records,
            supportability=InstrumentEligibilitySupportability(
                state=supportability_state,
                reason=supportability_reason,
                requested_count=len(request.security_ids),
                resolved_count=len(request.security_ids) - len(missing_security_ids),
                missing_security_ids=missing_security_ids,
            ),
            lineage={
                "source_system": "instrument_eligibility",
                "contract_version": "rfc_087_v1",
            },
            **source_product_runtime_metadata(
                request.as_of_date,
                data_quality_status=market_reference_data_quality_status(
                    rows,
                    required_count=len(request.security_ids),
                ),
                latest_evidence_timestamp=latest_reference_evidence_timestamp(rows),
            ),
        )

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

        after_sort_key: tuple[date, str] | None = None
        if cursor.get("last_acquisition_date") and cursor.get("last_lot_id"):
            after_sort_key = (
                date.fromisoformat(str(cursor["last_acquisition_date"])),
                str(cursor["last_lot_id"]),
            )

        rows = await self._buy_state_repository.list_portfolio_tax_lots(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            security_ids=request.security_ids,
            include_closed_lots=request.include_closed_lots,
            lot_status_filter=request.lot_status_filter,
            after_sort_key=after_sort_key,
            limit=request.page.page_size + 1,
        )
        has_more = len(rows) > request.page.page_size
        page_rows = rows[: request.page.page_size]

        lots = [
            portfolio_tax_lot_record(lot, local_currency=local_currency)
            for lot, local_currency in page_rows
        ]

        next_page_token: str | None = None
        if has_more and lots:
            last_lot = lots[-1]
            next_page_token = self._encode_page_token(
                {
                    "scope_fingerprint": request_scope_fingerprint,
                    "last_acquisition_date": last_lot.acquisition_date.isoformat(),
                    "last_lot_id": last_lot.lot_id,
                }
            )

        requested_security_ids = {
            normalize_security_id(security_id) for security_id in request.security_ids or []
        }
        returned_security_ids = {normalize_security_id(lot.security_id) for lot in lots}
        missing_security_ids = (
            [] if has_more else sorted(requested_security_ids - returned_security_ids)
        )
        supportability_state: Literal["READY", "DEGRADED", "INCOMPLETE", "UNAVAILABLE"] = "READY"
        supportability_reason = "TAX_LOTS_READY"
        if not lots and not request.security_ids:
            supportability_state = "UNAVAILABLE"
            supportability_reason = "TAX_LOTS_EMPTY"
        elif has_more:
            supportability_state = "DEGRADED"
            supportability_reason = "TAX_LOTS_PAGE_PARTIAL"
        elif request.security_ids and missing_security_ids:
            supportability_state = "INCOMPLETE"
            supportability_reason = "TAX_LOTS_MISSING_FOR_REQUESTED_SECURITIES"

        return PortfolioTaxLotWindowResponse(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            lots=lots,
            page=ReferencePageMetadata(
                page_size=request.page.page_size,
                sort_key="acquisition_date:asc,lot_id:asc",
                returned_component_count=len(lots),
                request_scope_fingerprint=request_scope_fingerprint,
                next_page_token=next_page_token,
            ),
            supportability=PortfolioTaxLotWindowSupportability(
                state=supportability_state,
                reason=supportability_reason,
                requested_security_count=(
                    len(request.security_ids) if request.security_ids is not None else None
                ),
                returned_lot_count=len(lots),
                missing_security_ids=missing_security_ids,
            ),
            lineage={
                "source_system": "position_lot_state",
                "contract_version": "rfc_087_v1",
            },
            **source_product_runtime_metadata_without_as_of_date(
                request.as_of_date,
                data_quality_status=(
                    "COMPLETE"
                    if supportability_state == "READY"
                    else "MISSING"
                    if supportability_state == "UNAVAILABLE"
                    else "PARTIAL"
                ),
                latest_evidence_timestamp=latest_reference_evidence_timestamp(
                    [lot for lot, _ in page_rows]
                ),
            ),
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

        curve_points = curve_page.points
        has_more = curve_page.has_more
        next_page_token: str | None = None
        if has_more and curve_points:
            last_point = curve_points[-1]
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

        requested_security_ids = {
            normalize_security_id(security_id) for security_id in request.security_ids or []
        }
        returned_security_ids = {key[0] for key in curve_page.all_curve_keys}
        missing_security_ids = sorted(requested_security_ids - returned_security_ids)

        supportability_state: Literal["READY", "DEGRADED", "INCOMPLETE", "UNAVAILABLE"] = "READY"
        supportability_reason = "TRANSACTION_COST_CURVE_READY"
        if not curve_page.all_curve_keys:
            supportability_state = "UNAVAILABLE"
            supportability_reason = "TRANSACTION_COST_EVIDENCE_NOT_FOUND"
        elif missing_security_ids:
            supportability_state = "INCOMPLETE"
            supportability_reason = "TRANSACTION_COST_EVIDENCE_MISSING_FOR_SECURITIES"
        elif has_more:
            supportability_state = "DEGRADED"
            supportability_reason = "TRANSACTION_COST_CURVE_PAGE_PARTIAL"

        return TransactionCostCurveResponse(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            window=request.window,
            curve_points=curve_points,
            page=ReferencePageMetadata(
                page_size=request.page.page_size,
                sort_key="security_id:asc,transaction_type:asc,currency:asc",
                returned_component_count=len(curve_points),
                request_scope_fingerprint=request_scope_fingerprint,
                next_page_token=next_page_token,
            ),
            supportability=TransactionCostCurveSupportability(
                state=supportability_state,
                reason=supportability_reason,
                requested_security_count=(
                    len(request.security_ids) if request.security_ids is not None else None
                ),
                returned_curve_point_count=len(curve_points),
                missing_security_ids=missing_security_ids,
            ),
            lineage={
                "source_system": "transactions",
                "contract_version": "rfc_040_wtbd_007_v1",
            },
            **source_product_runtime_metadata_without_as_of_date(
                request.as_of_date,
                data_quality_status="COMPLETE" if supportability_state == "READY" else "PARTIAL",
                latest_evidence_timestamp=latest_reference_evidence_timestamp(transactions),
            ),
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
