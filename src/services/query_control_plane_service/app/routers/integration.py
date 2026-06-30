from typing import NoReturn, cast

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, status
from portfolio_common.db import get_async_db_session
from portfolio_common.source_data_products import source_data_product_openapi_extra
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.dtos.core_snapshot_dto import (
    CoreSnapshotRequest,
    CoreSnapshotResponse,
    CoreSnapshotSection,
)
from src.services.query_service.app.dtos.integration_dto import (
    EffectiveIntegrationPolicyResponse,
    InstrumentEnrichmentBulkRequest,
    InstrumentEnrichmentBulkResponse,
)
from src.services.query_service.app.dtos.reference_integration_dto import (
    BenchmarkAssignmentRequest,
    BenchmarkAssignmentResponse,
    BenchmarkCatalogRequest,
    BenchmarkCatalogResponse,
    BenchmarkCompositionWindowRequest,
    BenchmarkCompositionWindowResponse,
    BenchmarkDefinitionRequest,
    BenchmarkDefinitionResponse,
    BenchmarkMarketSeriesRequest,
    BenchmarkMarketSeriesResponse,
    BenchmarkReturnSeriesRequest,
    BenchmarkReturnSeriesResponse,
    CioModelChangeAffectedCohortRequest,
    CioModelChangeAffectedCohortResponse,
    ClassificationTaxonomyRequest,
    ClassificationTaxonomyResponse,
    ClientIncomeNeedsScheduleRequest,
    ClientIncomeNeedsScheduleResponse,
    ClientRestrictionProfileRequest,
    ClientRestrictionProfileResponse,
    ClientTaxProfileRequest,
    ClientTaxProfileResponse,
    ClientTaxRuleSetRequest,
    ClientTaxRuleSetResponse,
    CoverageRequest,
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
    IndexCatalogRequest,
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
    PerformanceComponentEconomicsRequest,
    PerformanceComponentEconomicsResponse,
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
from src.services.query_service.app.services.core_snapshot_service import (
    CoreSnapshotBadRequestError,
    CoreSnapshotConflictError,
    CoreSnapshotNotFoundError,
    CoreSnapshotService,
    CoreSnapshotUnavailableSectionError,
    SnapshotGovernanceContext,
)
from src.services.query_service.app.services.integration_service import IntegrationService

from .response_helpers import (
    problem_example,
    problem_or_validation_response,
    problem_response,
    raise_problem,
)

router = APIRouter(prefix="/integration", tags=["Integration Contracts"])


def _integration_source_not_found_example(
    *,
    source_product: str,
    detail: str,
    metadata: dict[str, object] | None = None,
    instance: str = "/integration/portfolios/PORT-INT-001/benchmark-assignment",
) -> dict[str, object]:
    return problem_example(
        status_code=status.HTTP_404_NOT_FOUND,
        title="Integration source data not found",
        detail=detail,
        error_code="QCP_INTEGRATION_SOURCE_NOT_FOUND",
        instance=instance,
        metadata={"source_product": source_product, **(metadata or {})},
    )


def _integration_source_invalid_request_example(
    *,
    source_product: str,
    detail: str,
    metadata: dict[str, object] | None = None,
    instance: str = "/integration/dpm/portfolio-universe/candidates",
) -> dict[str, object]:
    return problem_example(
        status_code=422,
        title="Integration source request is invalid",
        detail=detail,
        error_code="QCP_INTEGRATION_SOURCE_INVALID_REQUEST",
        instance=instance,
        metadata={"source_product": source_product, **(metadata or {})},
    )


def _integration_source_conflict_example(
    *,
    source_product: str,
    detail: str,
    metadata: dict[str, object] | None = None,
    instance: str = "/integration/benchmarks/BMK_GLOBAL_BALANCED_60_40/composition-window",
) -> dict[str, object]:
    return problem_example(
        status_code=status.HTTP_409_CONFLICT,
        title="Integration source data conflict",
        detail=detail,
        error_code="QCP_INTEGRATION_SOURCE_CONFLICT",
        instance=instance,
        metadata={"source_product": source_product, **(metadata or {})},
    )


INTEGRATION_POLICY_BLOCKED_EXAMPLE = problem_example(
    status_code=status.HTTP_403_FORBIDDEN,
    title="Core snapshot sections blocked by policy",
    detail="Requested snapshot sections are blocked by strict integration policy.",
    error_code="QCP_CORE_SNAPSHOT_POLICY_BLOCKED",
    metadata={"source_product": "PortfolioStateSnapshot"},
)
CORE_SNAPSHOT_INVALID_REQUEST_EXAMPLE = problem_example(
    status_code=status.HTTP_400_BAD_REQUEST,
    title="Core snapshot request is invalid",
    detail="Core snapshot request is invalid.",
    error_code="QCP_CORE_SNAPSHOT_INVALID_REQUEST",
    metadata={"source_product": "PortfolioStateSnapshot"},
)
CORE_SNAPSHOT_NOT_FOUND_EXAMPLE = problem_example(
    status_code=status.HTTP_404_NOT_FOUND,
    title="Core snapshot not found",
    detail="Portfolio or simulation session was not found.",
    error_code="QCP_CORE_SNAPSHOT_NOT_FOUND",
    metadata={"source_product": "PortfolioStateSnapshot"},
)
CORE_SNAPSHOT_CONFLICT_EXAMPLE = problem_example(
    status_code=status.HTTP_409_CONFLICT,
    title="Core snapshot conflict",
    detail="Core snapshot request conflicts with the current portfolio or simulation state.",
    error_code="QCP_CORE_SNAPSHOT_CONFLICT",
    metadata={"source_product": "PortfolioStateSnapshot"},
)
CORE_SNAPSHOT_UNAVAILABLE_EXAMPLE = problem_example(
    status_code=422,
    title="Core snapshot section unavailable",
    detail="Requested core snapshot section cannot be fulfilled from available source data.",
    error_code="QCP_CORE_SNAPSHOT_UNAVAILABLE_SECTION",
    metadata={"source_product": "PortfolioStateSnapshot"},
)
INSTRUMENT_ENRICHMENT_INVALID_DETAIL = "Instrument enrichment request is invalid."
INSTRUMENT_ENRICHMENT_INVALID_EXAMPLE = problem_example(
    status_code=status.HTTP_400_BAD_REQUEST,
    title="Instrument enrichment request is invalid",
    detail=INSTRUMENT_ENRICHMENT_INVALID_DETAIL,
    error_code="QCP_INSTRUMENT_ENRICHMENT_INVALID_REQUEST",
    instance="/integration/instruments/enrichment-bulk",
    metadata={
        "source_product": "InstrumentReferenceBundle",
        "reason": "CoreSnapshotBadRequestError",
    },
)
BENCHMARK_ASSIGNMENT_NOT_FOUND_DETAIL = (
    "No effective benchmark assignment found for portfolio and as_of_date."
)
BENCHMARK_ASSIGNMENT_NOT_FOUND_EXAMPLE = _integration_source_not_found_example(
    source_product="BenchmarkAssignment",
    detail=BENCHMARK_ASSIGNMENT_NOT_FOUND_DETAIL,
    metadata={"portfolio_id": "PORT-INT-001", "reason": "not_found"},
)
MODEL_PORTFOLIO_TARGET_NOT_FOUND_DETAIL = (
    "No approved model portfolio target found for model_portfolio_id and as_of_date."
)
MODEL_PORTFOLIO_TARGET_NOT_FOUND_EXAMPLE = _integration_source_not_found_example(
    source_product="DpmModelPortfolioTarget",
    detail=MODEL_PORTFOLIO_TARGET_NOT_FOUND_DETAIL,
    metadata={"model_portfolio_id": "MODEL_SG_BALANCED_DPM", "reason": "not_found"},
    instance="/integration/model-portfolios/MODEL_SG_BALANCED_DPM/targets",
)
PORTFOLIO_MANAGER_BOOK_EMPTY_DETAIL = (
    "No portfolio memberships found for portfolio_manager_id and request filters."
)
PORTFOLIO_MANAGER_BOOK_EMPTY_EXAMPLE = _integration_source_not_found_example(
    source_product="PortfolioManagerBookMembership",
    detail=PORTFOLIO_MANAGER_BOOK_EMPTY_DETAIL,
    metadata={"portfolio_manager_id": "PM_SG_DPM_001", "reason": "empty_result"},
    instance="/integration/portfolio-manager-books/PM_SG_DPM_001/memberships",
)
CIO_MODEL_CHANGE_AFFECTED_COHORT_EMPTY_DETAIL = (
    "No affected mandates found for model_portfolio_id and request filters."
)
CIO_MODEL_CHANGE_AFFECTED_COHORT_EMPTY_EXAMPLE = _integration_source_not_found_example(
    source_product="CioModelChangeAffectedCohort",
    detail=CIO_MODEL_CHANGE_AFFECTED_COHORT_EMPTY_DETAIL,
    metadata={"model_portfolio_id": "MODEL_PB_SG_GLOBAL_BAL_DPM", "reason": "empty_result"},
    instance="/integration/model-portfolios/MODEL_PB_SG_GLOBAL_BAL_DPM/affected-mandates",
)
DPM_PORTFOLIO_UNIVERSE_EMPTY_DETAIL = (
    "No DPM portfolio-universe candidates found for request filters."
)
DPM_PORTFOLIO_UNIVERSE_INVALID_REQUEST_DETAIL = "DPM portfolio-universe request is invalid."
DPM_PORTFOLIO_UNIVERSE_EMPTY_EXAMPLE = _integration_source_not_found_example(
    source_product="DpmPortfolioUniverseCandidate",
    detail=DPM_PORTFOLIO_UNIVERSE_EMPTY_DETAIL,
    metadata={"reason": "empty_result"},
    instance="/integration/dpm/portfolio-universe/candidates",
)
DPM_PORTFOLIO_UNIVERSE_INVALID_REQUEST_EXAMPLE = _integration_source_invalid_request_example(
    source_product="DpmPortfolioUniverseCandidate",
    detail=DPM_PORTFOLIO_UNIVERSE_INVALID_REQUEST_DETAIL,
    metadata={"reason": "ValueError"},
)
MANDATE_BINDING_NOT_FOUND_DETAIL = (
    "No effective discretionary mandate binding found for portfolio and as_of_date."
)
MANDATE_BINDING_NOT_FOUND_EXAMPLE = _integration_source_not_found_example(
    source_product="DiscretionaryMandateBinding",
    detail=MANDATE_BINDING_NOT_FOUND_DETAIL,
    metadata={"portfolio_id": "PB_SG_GLOBAL_BAL_001", "reason": "not_found"},
    instance="/integration/portfolios/PB_SG_GLOBAL_BAL_001/mandate-binding",
)


def _mandate_scoped_source_not_found_example(
    *,
    source_product: str,
    route_suffix: str,
) -> dict[str, object]:
    return _integration_source_not_found_example(
        source_product=source_product,
        detail=MANDATE_BINDING_NOT_FOUND_DETAIL,
        metadata={"portfolio_id": "PB_SG_GLOBAL_BAL_001", "reason": "not_found"},
        instance=f"/integration/portfolios/PB_SG_GLOBAL_BAL_001/{route_suffix}",
    )


CLIENT_RESTRICTION_PROFILE_NOT_FOUND_EXAMPLE = _mandate_scoped_source_not_found_example(
    source_product="ClientRestrictionProfile",
    route_suffix="client-restriction-profile",
)
SUSTAINABILITY_PREFERENCE_PROFILE_NOT_FOUND_EXAMPLE = _mandate_scoped_source_not_found_example(
    source_product="SustainabilityPreferenceProfile",
    route_suffix="sustainability-preference-profile",
)
CLIENT_TAX_PROFILE_NOT_FOUND_EXAMPLE = _mandate_scoped_source_not_found_example(
    source_product="ClientTaxProfile",
    route_suffix="client-tax-profile",
)
CLIENT_TAX_RULE_SET_NOT_FOUND_EXAMPLE = _mandate_scoped_source_not_found_example(
    source_product="ClientTaxRuleSet",
    route_suffix="client-tax-rule-set",
)
CLIENT_INCOME_NEEDS_SCHEDULE_NOT_FOUND_EXAMPLE = _mandate_scoped_source_not_found_example(
    source_product="ClientIncomeNeedsSchedule",
    route_suffix="client-income-needs-schedule",
)
LIQUIDITY_RESERVE_REQUIREMENT_NOT_FOUND_EXAMPLE = _mandate_scoped_source_not_found_example(
    source_product="LiquidityReserveRequirement",
    route_suffix="liquidity-reserve-requirement",
)
PLANNED_WITHDRAWAL_SCHEDULE_NOT_FOUND_EXAMPLE = _mandate_scoped_source_not_found_example(
    source_product="PlannedWithdrawalSchedule",
    route_suffix="planned-withdrawal-schedule",
)
EXTERNAL_HEDGE_POLICY_NOT_FOUND_EXAMPLE = _mandate_scoped_source_not_found_example(
    source_product="ExternalHedgePolicy",
    route_suffix="external-hedge-policy",
)
EXTERNAL_HEDGE_EXECUTION_READINESS_NOT_FOUND_EXAMPLE = _mandate_scoped_source_not_found_example(
    source_product="ExternalHedgeExecutionReadiness",
    route_suffix="external-hedge-execution-readiness",
)
EXTERNAL_ORDER_EXECUTION_ACKNOWLEDGEMENT_NOT_FOUND_EXAMPLE = (
    _mandate_scoped_source_not_found_example(
        source_product="ExternalOrderExecutionAcknowledgement",
        route_suffix="external-order-execution-acknowledgement",
    )
)
EXTERNAL_CURRENCY_EXPOSURE_NOT_FOUND_EXAMPLE = _mandate_scoped_source_not_found_example(
    source_product="ExternalCurrencyExposure",
    route_suffix="external-currency-exposure",
)
EXTERNAL_ELIGIBLE_HEDGE_INSTRUMENT_NOT_FOUND_EXAMPLE = _mandate_scoped_source_not_found_example(
    source_product="ExternalEligibleHedgeInstrument",
    route_suffix="external-eligible-hedge-instruments",
)
PORTFOLIO_TAX_LOTS_NOT_FOUND_EXAMPLE = problem_example(
    status_code=status.HTTP_404_NOT_FOUND,
    title="Portfolio source evidence not found",
    detail="Requested portfolio source evidence was not found.",
    error_code="QCP_SOURCE_EVIDENCE_NOT_FOUND",
    metadata={
        "source_product": "PortfolioTaxLotWindow",
        "portfolio_id": "PB_SG_GLOBAL_BAL_001",
    },
)
BENCHMARK_DEFINITION_NOT_FOUND_DETAIL = (
    "No effective benchmark definition found for benchmark_id and as_of_date."
)
BENCHMARK_DEFINITION_NOT_FOUND_EXAMPLE = _integration_source_not_found_example(
    source_product="BenchmarkDefinition",
    detail=BENCHMARK_DEFINITION_NOT_FOUND_DETAIL,
    metadata={"benchmark_id": "BMK_GLOBAL_BALANCED_60_40", "reason": "not_found"},
    instance="/integration/benchmarks/BMK_GLOBAL_BALANCED_60_40/definition",
)
BENCHMARK_COMPOSITION_WINDOW_NOT_FOUND_DETAIL = (
    "No overlapping benchmark definition found for benchmark_id and requested window."
)
BENCHMARK_COMPOSITION_WINDOW_NOT_FOUND_EXAMPLE = _integration_source_not_found_example(
    source_product="BenchmarkConstituentWindow",
    detail=BENCHMARK_COMPOSITION_WINDOW_NOT_FOUND_DETAIL,
    metadata={"benchmark_id": "BMK_GLOBAL_BALANCED_60_40", "reason": "not_found"},
    instance="/integration/benchmarks/BMK_GLOBAL_BALANCED_60_40/composition-window",
)
BENCHMARK_COMPOSITION_WINDOW_CONFLICT_DETAIL = (
    "Benchmark composition window request conflicts with effective benchmark definition data."
)
BENCHMARK_COMPOSITION_WINDOW_CONFLICT_EXAMPLE = _integration_source_conflict_example(
    source_product="BenchmarkConstituentWindow",
    detail=BENCHMARK_COMPOSITION_WINDOW_CONFLICT_DETAIL,
    metadata={"benchmark_id": "BMK_GLOBAL_BALANCED_60_40", "reason": "ValueError"},
)
TRANSACTION_COST_CURVE_NOT_FOUND_EXAMPLE = problem_example(
    status_code=status.HTTP_404_NOT_FOUND,
    title="Portfolio source evidence not found",
    detail="Requested portfolio source evidence was not found.",
    error_code="QCP_SOURCE_EVIDENCE_NOT_FOUND",
    metadata={
        "source_product": "TransactionCostCurve",
        "portfolio_id": "PB_SG_GLOBAL_BAL_001",
    },
)
PERFORMANCE_COMPONENT_ECONOMICS_NOT_FOUND_EXAMPLE = problem_example(
    status_code=status.HTTP_404_NOT_FOUND,
    title="Portfolio source evidence not found",
    detail="Requested portfolio source evidence was not found.",
    error_code="QCP_SOURCE_EVIDENCE_NOT_FOUND",
    metadata={
        "source_product": "PerformanceComponentEconomics",
        "portfolio_id": "PB_SG_GLOBAL_BAL_001",
    },
)
SOURCE_EVIDENCE_INVALID_REQUEST_EXAMPLE = problem_example(
    status_code=status.HTTP_400_BAD_REQUEST,
    title="Portfolio source evidence request is invalid",
    detail="Portfolio source evidence request is invalid.",
    error_code="QCP_SOURCE_EVIDENCE_INVALID_REQUEST",
    metadata={
        "source_product": "PerformanceComponentEconomics",
        "portfolio_id": "PB_SG_GLOBAL_BAL_001",
    },
)
HTTP_422_UNPROCESSABLE_CONTENT = 422


def get_integration_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> IntegrationService:
    return IntegrationService(db)


def get_core_snapshot_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> CoreSnapshotService:
    return CoreSnapshotService(db)


def _raise_integration_source_not_found(
    *,
    source_product: str,
    detail: str,
    metadata: dict[str, object] | None = None,
) -> NoReturn:
    raise_problem(
        status_code=status.HTTP_404_NOT_FOUND,
        title="Integration source data not found",
        detail=detail,
        error_code="QCP_INTEGRATION_SOURCE_NOT_FOUND",
        metadata={"source_product": source_product, **(metadata or {})},
    )


def _raise_mandate_scoped_source_not_found(
    *,
    source_product: str,
    portfolio_id: str,
) -> NoReturn:
    _raise_integration_source_not_found(
        source_product=source_product,
        detail=MANDATE_BINDING_NOT_FOUND_DETAIL,
        metadata={"portfolio_id": portfolio_id, "reason": "not_found"},
    )


def _raise_integration_source_invalid_request(
    *,
    source_product: str,
    detail: str,
    exc: Exception,
    metadata: dict[str, object] | None = None,
) -> NoReturn:
    raise_problem(
        status_code=HTTP_422_UNPROCESSABLE_CONTENT,
        title="Integration source request is invalid",
        detail=detail,
        error_code="QCP_INTEGRATION_SOURCE_INVALID_REQUEST",
        metadata={
            "source_product": source_product,
            "reason": exc.__class__.__name__,
            **(metadata or {}),
        },
    )


def _raise_integration_source_conflict(
    *,
    source_product: str,
    detail: str,
    exc: Exception,
    metadata: dict[str, object] | None = None,
) -> NoReturn:
    raise_problem(
        status_code=status.HTTP_409_CONFLICT,
        title="Integration source data conflict",
        detail=detail,
        error_code="QCP_INTEGRATION_SOURCE_CONFLICT",
        metadata={
            "source_product": source_product,
            "reason": exc.__class__.__name__,
            **(metadata or {}),
        },
    )


def _raise_instrument_enrichment_invalid_request(exc: Exception) -> NoReturn:
    raise_problem(
        status_code=status.HTTP_400_BAD_REQUEST,
        title="Instrument enrichment request is invalid",
        detail=INSTRUMENT_ENRICHMENT_INVALID_DETAIL,
        error_code="QCP_INSTRUMENT_ENRICHMENT_INVALID_REQUEST",
        metadata={
            "source_product": "InstrumentReferenceBundle",
            "reason": exc.__class__.__name__,
        },
    )


def _raise_source_evidence_problem(
    *,
    status_code: int,
    title: str,
    detail: str,
    error_code: str,
    source_product: str,
    portfolio_id: str,
    reason: str,
) -> NoReturn:
    raise_problem(
        status_code=status_code,
        title=title,
        detail=detail,
        error_code=error_code,
        metadata={
            "source_product": source_product,
            "portfolio_id": portfolio_id,
            "reason": reason,
        },
    )


def _raise_source_evidence_not_found(
    *,
    source_product: str,
    portfolio_id: str,
    exc: Exception,
) -> NoReturn:
    _raise_source_evidence_problem(
        status_code=status.HTTP_404_NOT_FOUND,
        title="Portfolio source evidence not found",
        detail="Requested portfolio source evidence was not found.",
        error_code="QCP_SOURCE_EVIDENCE_NOT_FOUND",
        source_product=source_product,
        portfolio_id=portfolio_id,
        reason=exc.__class__.__name__,
    )


def _raise_source_evidence_invalid_request(
    *,
    source_product: str,
    portfolio_id: str,
    exc: Exception,
) -> NoReturn:
    _raise_source_evidence_problem(
        status_code=status.HTTP_400_BAD_REQUEST,
        title="Portfolio source evidence request is invalid",
        detail="Portfolio source evidence request is invalid.",
        error_code="QCP_SOURCE_EVIDENCE_INVALID_REQUEST",
        source_product=source_product,
        portfolio_id=portfolio_id,
        reason=exc.__class__.__name__,
    )


@router.get(
    "/policy/effective",
    response_model=EffectiveIntegrationPolicyResponse,
    summary="Get effective lotus-core integration policy",
    description=(
        "What: Return effective integration policy diagnostics for a consumer and tenant "
        "context.\n"
        "How: Resolves the canonical policy rule, reports policy provenance, and optionally "
        "evaluates requested snapshot sections through `include_sections`.\n"
        "When: Used directly by lotus-gateway platform/bootstrap flows, operator tooling, and "
        "other downstream clients that need to inspect lotus-core section policy before calling "
        "governed source-data routes such as "
        "`/integration/portfolios/{portfolio_id}/core-snapshot`. This route returns policy "
        "diagnostics only; it does not publish portfolio state or analytics inputs. Callers must "
        "use the canonical snake_case query parameters `consumer_system` and `tenant_id`; "
        "camelCase aliases such as `consumerSystem` and `tenantId` are not supported."
    ),
)
async def get_effective_integration_policy(
    consumer_system: str = Query(
        "lotus-gateway",
        description="Downstream consumer system requesting policy resolution.",
        examples=["lotus-performance"],
    ),
    tenant_id: str = Query(
        "default",
        description="Tenant identifier used for policy resolution.",
        examples=["tenant_sg_pb"],
    ),
    include_sections: list[str] | None = Query(
        None,
        description="Optional requested snapshot sections to evaluate against policy.",
        examples=["positions_baseline", "portfolio_totals"],
    ),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> EffectiveIntegrationPolicyResponse:
    response = integration_service.get_effective_policy(
        consumer_system=consumer_system,
        tenant_id=tenant_id,
        include_sections=include_sections,
    )
    return cast(EffectiveIntegrationPolicyResponse, response)


@router.post(
    "/portfolios/{portfolio_id}/core-snapshot",
    response_model=CoreSnapshotResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: problem_response(
            "Invalid request payload or invalid section/mode combination.",
            CORE_SNAPSHOT_INVALID_REQUEST_EXAMPLE,
        ),
        status.HTTP_403_FORBIDDEN: problem_response(
            "Requested sections are blocked by strict integration policy.",
            INTEGRATION_POLICY_BLOCKED_EXAMPLE,
        ),
        status.HTTP_404_NOT_FOUND: problem_response(
            "Portfolio or simulation session not found.",
            CORE_SNAPSHOT_NOT_FOUND_EXAMPLE,
        ),
        status.HTTP_409_CONFLICT: problem_response(
            "Simulation expected version mismatch or portfolio/session conflict.",
            CORE_SNAPSHOT_CONFLICT_EXAMPLE,
        ),
        HTTP_422_UNPROCESSABLE_CONTENT: problem_or_validation_response(
            "Section cannot be fulfilled due to missing valuation dependencies.",
            CORE_SNAPSHOT_UNAVAILABLE_EXAMPLE,
        ),
    },
    summary="Fetch governed core snapshot contract",
    description=(
        "What: Return a governed multi-section portfolio snapshot contract for downstream "
        "integration consumers.\n"
        "How: Applies tenant and consumer policy, resolves baseline or simulation state, "
        "and returns reproducibility metadata including request fingerprint and freshness.\n"
        "When: Used directly by lotus-gateway workspace state sourcing and lotus-risk "
        "concentration or rolling-Sharpe context flows that need policy-aware positions, "
        "totals, delta, or enrichment views without direct query-service coupling. Other "
        "downstream consumers may adopt it later, but this route publishes portfolio-state "
        "source data, not downstream analytics conclusions such as performance returns, "
        "risk metrics, or advisory recommendation ownership.\n"
        "Contract note: the governed response does not publish a legacy nested `portfolio` "
        "or `metadata` envelope. Consumer context should be read from the top-level "
        "source-data runtime metadata, `valuation_context`, and the requested `sections`."
    ),
    openapi_extra=source_data_product_openapi_extra("PortfolioStateSnapshot"),
)
async def create_core_snapshot(
    request: CoreSnapshotRequest,
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier for the snapshot request.",
        examples=["PORT-INT-001"],
    ),
    service: CoreSnapshotService = Depends(get_core_snapshot_service),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> CoreSnapshotResponse:
    effective_request, governance = _governed_core_snapshot_request(
        request=request,
        integration_service=integration_service,
    )
    return await _core_snapshot_response_or_http_error(
        service=service,
        portfolio_id=portfolio_id,
        request=effective_request,
        governance=governance,
    )


def _governed_core_snapshot_request(
    *,
    request: CoreSnapshotRequest,
    integration_service: IntegrationService,
) -> tuple[CoreSnapshotRequest, SnapshotGovernanceContext]:
    requested_sections = list(request.sections)
    policy = integration_service.get_effective_policy(
        consumer_system=request.consumer_system,
        tenant_id=request.tenant_id,
        include_sections=_policy_section_codes(requested_sections),
    )
    applied_sections, dropped_sections, warnings = _policy_applied_snapshot_sections(
        requested_sections=requested_sections,
        policy=policy,
    )
    _assert_core_snapshot_sections_allowed(
        applied_sections=applied_sections,
        dropped_sections=dropped_sections,
        strict_mode=policy.policy_provenance.strict_mode,
    )
    return (
        request.model_copy(update={"sections": applied_sections}),
        _core_snapshot_governance(
            policy=policy,
            requested_sections=requested_sections,
            applied_sections=applied_sections,
            dropped_sections=dropped_sections,
            warnings=warnings,
        ),
    )


def _policy_section_codes(sections: list[CoreSnapshotSection]) -> list[str]:
    return [section.value.upper() for section in sections]


def _policy_applied_snapshot_sections(
    *,
    requested_sections: list[CoreSnapshotSection],
    policy,
) -> tuple[list[CoreSnapshotSection], list[CoreSnapshotSection], list[str]]:
    if "NO_ALLOWED_SECTION_RESTRICTION" in policy.warnings:
        return requested_sections, [], list(policy.warnings)

    allowed_policy_sections = set(policy.allowed_sections)
    applied_sections = [
        section
        for section in requested_sections
        if section.value.upper() in allowed_policy_sections
    ]
    dropped_sections = [
        section
        for section in requested_sections
        if section.value.upper() not in allowed_policy_sections
    ]
    warnings = list(policy.warnings)
    if dropped_sections and not policy.policy_provenance.strict_mode:
        warnings.append("SECTIONS_DROPPED_NON_STRICT_MODE")
    return applied_sections, dropped_sections, warnings


def _assert_core_snapshot_sections_allowed(
    *,
    applied_sections: list[CoreSnapshotSection],
    dropped_sections: list[CoreSnapshotSection],
    strict_mode: bool,
) -> None:
    if dropped_sections and strict_mode:
        raise_problem(
            status_code=status.HTTP_403_FORBIDDEN,
            title="Core snapshot sections blocked by policy",
            detail="Requested snapshot sections are blocked by strict integration policy.",
            error_code="QCP_CORE_SNAPSHOT_POLICY_BLOCKED",
            metadata={
                "source_product": "PortfolioStateSnapshot",
                "blocked_sections": [section.value for section in dropped_sections],
            },
        )

    if not applied_sections:
        raise_problem(
            status_code=status.HTTP_400_BAD_REQUEST,
            title="Core snapshot request is invalid",
            detail="No core snapshot sections remain after policy evaluation.",
            error_code="QCP_CORE_SNAPSHOT_INVALID_REQUEST",
            metadata={"source_product": "PortfolioStateSnapshot"},
        )


def _core_snapshot_governance(
    *,
    policy,
    requested_sections: list[CoreSnapshotSection],
    applied_sections: list[CoreSnapshotSection],
    dropped_sections: list[CoreSnapshotSection],
    warnings: list[str],
) -> SnapshotGovernanceContext:
    return SnapshotGovernanceContext(
        consumer_system=policy.consumer_system,
        tenant_id=policy.tenant_id,
        requested_sections=requested_sections,
        applied_sections=applied_sections,
        dropped_sections=dropped_sections,
        policy_version=policy.policy_provenance.policy_version,
        policy_source=policy.policy_provenance.policy_source,
        matched_rule_id=policy.policy_provenance.matched_rule_id,
        strict_mode=policy.policy_provenance.strict_mode,
        warnings=warnings,
    )


async def _core_snapshot_response_or_http_error(
    *,
    service: CoreSnapshotService,
    portfolio_id: str,
    request: CoreSnapshotRequest,
    governance: SnapshotGovernanceContext,
) -> CoreSnapshotResponse:
    try:
        response = await service.get_core_snapshot(
            portfolio_id=portfolio_id,
            request=request,
            governance=governance,
        )
        return cast(CoreSnapshotResponse, response)
    except CoreSnapshotBadRequestError as exc:
        raise_problem(
            status_code=status.HTTP_400_BAD_REQUEST,
            title="Core snapshot request is invalid",
            detail="Core snapshot request is invalid.",
            error_code="QCP_CORE_SNAPSHOT_INVALID_REQUEST",
            metadata={"source_product": "PortfolioStateSnapshot", "reason": exc.__class__.__name__},
        )
    except CoreSnapshotNotFoundError as exc:
        raise_problem(
            status_code=status.HTTP_404_NOT_FOUND,
            title="Core snapshot not found",
            detail="Portfolio or simulation session was not found.",
            error_code="QCP_CORE_SNAPSHOT_NOT_FOUND",
            metadata={"source_product": "PortfolioStateSnapshot", "reason": exc.__class__.__name__},
        )
    except CoreSnapshotConflictError as exc:
        raise_problem(
            status_code=status.HTTP_409_CONFLICT,
            title="Core snapshot conflict",
            detail=(
                "Core snapshot request conflicts with the current portfolio or simulation state."
            ),
            error_code="QCP_CORE_SNAPSHOT_CONFLICT",
            metadata={"source_product": "PortfolioStateSnapshot", "reason": exc.__class__.__name__},
        )
    except CoreSnapshotUnavailableSectionError as exc:
        raise_problem(
            status_code=HTTP_422_UNPROCESSABLE_CONTENT,
            title="Core snapshot section unavailable",
            detail=(
                "Requested core snapshot section cannot be fulfilled from available source data."
            ),
            error_code="QCP_CORE_SNAPSHOT_UNAVAILABLE_SECTION",
            metadata={"source_product": "PortfolioStateSnapshot", "reason": exc.__class__.__name__},
        )


@router.post(
    "/instruments/enrichment-bulk",
    response_model=InstrumentEnrichmentBulkResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: problem_response(
            "Invalid request payload.",
            INSTRUMENT_ENRICHMENT_INVALID_EXAMPLE,
        ),
    },
    summary="Resolve issuer enrichment for security identifiers",
    description=(
        "What: Return source-owned issuer and liquidity enrichment for a caller-provided "
        "security_id list.\n"
        "How: Resolves canonical instrument metadata in one deterministic batch, preserves "
        "request order, and returns null issuer fields for unknown securities instead of "
        "inventing fallback identities.\n"
        "When: Used directly by lotus-advise and lotus-risk when shared instrument reference "
        "context is needed without direct query-service coupling. Other downstream consumers "
        "such as lotus-performance or lotus-gateway may adopt the same governed enrichment "
        "contract when they need source-owned reference context."
    ),
    openapi_extra=source_data_product_openapi_extra("InstrumentReferenceBundle"),
)
async def get_instrument_enrichment_bulk(
    request: InstrumentEnrichmentBulkRequest,
    service: CoreSnapshotService = Depends(get_core_snapshot_service),
) -> InstrumentEnrichmentBulkResponse:
    try:
        records = await service.get_instrument_enrichment_bulk(request.security_ids)
        return InstrumentEnrichmentBulkResponse(records=records)
    except CoreSnapshotBadRequestError as exc:
        _raise_instrument_enrichment_invalid_request(exc)


@router.post(
    "/instruments/eligibility-bulk",
    response_model=InstrumentEligibilityBulkResponse,
    summary="Resolve DPM instrument eligibility profiles",
    description=(
        "What: Return effective DPM instrument eligibility, product shelf, restriction code, "
        "liquidity, issuer, and settlement profile records for a caller-provided security list.\n"
        "How: Resolves effective-dated eligibility records in one deterministic batch, preserves "
        "request order, and returns explicit UNKNOWN records for missing securities instead of "
        "inventing local fallback truth.\n"
        "When: Use this endpoint when lotus-manage assembles stateful DPM shelf inputs for held "
        "and target instruments. Do not use it as a general instrument search API or to retrieve "
        "operator-only free-text restriction rationale."
    ),
    openapi_extra=source_data_product_openapi_extra("InstrumentEligibilityProfile"),
)
async def resolve_instrument_eligibility_bulk(
    request: InstrumentEligibilityBulkRequest,
    integration_service: IntegrationService = Depends(get_integration_service),
) -> InstrumentEligibilityBulkResponse:
    return await integration_service.resolve_instrument_eligibility_bulk(request)


@router.post(
    "/portfolios/{portfolio_id}/tax-lots",
    response_model=PortfolioTaxLotWindowResponse,
    summary="Resolve DPM portfolio tax-lot window",
    description=(
        "What: Return current tax-lot and cost-basis state for all or selected securities in a "
        "portfolio window.\n"
        "How: Reads the authoritative `position_lot_state` records in one paged portfolio-window "
        "call, preserving acquisition-date ordering for tax-aware sell allocation and avoiding "
        "per-security production fan-out.\n"
        "When: Use this endpoint when lotus-manage assembles tax-aware DPM sell context for a "
        "governed portfolio. Do not use it as a general transaction history endpoint; use the "
        "operational transaction routes for ledger browsing."
    ),
    responses={
        404: problem_response(
            "Portfolio not found",
            PORTFOLIO_TAX_LOTS_NOT_FOUND_EXAMPLE,
        ),
        400: problem_response(
            "Invalid page token",
            problem_example(
                status_code=status.HTTP_400_BAD_REQUEST,
                title="Portfolio source evidence request is invalid",
                detail="Portfolio source evidence request is invalid.",
                error_code="QCP_SOURCE_EVIDENCE_INVALID_REQUEST",
                metadata={
                    "source_product": "PortfolioTaxLotWindow",
                    "portfolio_id": "PB_SG_GLOBAL_BAL_001",
                },
            ),
        ),
    },
    openapi_extra=source_data_product_openapi_extra("PortfolioTaxLotWindow"),
)
async def get_portfolio_tax_lot_window(
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier whose tax-lot window should be returned.",
        examples=["PB_SG_GLOBAL_BAL_001"],
    ),
    request: PortfolioTaxLotWindowRequest = Body(...),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> PortfolioTaxLotWindowResponse:
    try:
        return await integration_service.get_portfolio_tax_lot_window(
            portfolio_id=portfolio_id,
            request=request,
        )
    except LookupError as exc:
        _raise_source_evidence_not_found(
            source_product="PortfolioTaxLotWindow",
            portfolio_id=portfolio_id,
            exc=exc,
        )
    except ValueError as exc:
        _raise_source_evidence_invalid_request(
            source_product="PortfolioTaxLotWindow",
            portfolio_id=portfolio_id,
            exc=exc,
        )


@router.post(
    "/portfolios/{portfolio_id}/transaction-cost-curve",
    response_model=TransactionCostCurveResponse,
    summary="Resolve observed transaction-cost curve",
    description=(
        "What: Return source-owned observed transaction-cost evidence for a portfolio window.\n"
        "How: Reads booked transaction fees and fee components from lotus-core transactions, "
        "groups them by security, transaction type, and currency, and publishes observed "
        "basis-point cost points with lineage. The response is evidence from booked data, not "
        "a predictive market-impact quote or execution promise.\n"
        "When: Use this endpoint when lotus-manage needs to distinguish source-backed transaction "
        "cost evidence from local estimated construction cost in DPM proof packs."
    ),
    responses={
        404: problem_response(
            "Portfolio not found",
            TRANSACTION_COST_CURVE_NOT_FOUND_EXAMPLE,
        ),
        400: problem_response(
            "Invalid transaction-cost curve request",
            problem_example(
                status_code=status.HTTP_400_BAD_REQUEST,
                title="Portfolio source evidence request is invalid",
                detail="Portfolio source evidence request is invalid.",
                error_code="QCP_SOURCE_EVIDENCE_INVALID_REQUEST",
                metadata={
                    "source_product": "TransactionCostCurve",
                    "portfolio_id": "PB_SG_GLOBAL_BAL_001",
                },
            ),
        ),
    },
    openapi_extra=source_data_product_openapi_extra("TransactionCostCurve"),
)
async def get_transaction_cost_curve(
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier whose observed transaction-cost evidence is requested.",
        examples=["PB_SG_GLOBAL_BAL_001"],
    ),
    request: TransactionCostCurveRequest = Body(...),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> TransactionCostCurveResponse:
    try:
        return await integration_service.get_transaction_cost_curve(
            portfolio_id=portfolio_id,
            request=request,
        )
    except LookupError as exc:
        _raise_source_evidence_not_found(
            source_product="TransactionCostCurve",
            portfolio_id=portfolio_id,
            exc=exc,
        )
    except ValueError as exc:
        _raise_source_evidence_invalid_request(
            source_product="TransactionCostCurve",
            portfolio_id=portfolio_id,
            exc=exc,
        )


@router.post(
    "/portfolios/{portfolio_id}/performance-component-economics",
    response_model=PerformanceComponentEconomicsResponse,
    summary="Resolve performance component economics source evidence",
    description=(
        "What: Return source-authored transaction, cashflow, fee, tax, income, realized P&L, "
        "and FX-context economics evidence for contribution analytics.\n"
        "How: Reads core transaction rows with linked cashflow and transaction-cost records, "
        "returns deterministic row-level evidence plus component-family totals and coverage "
        "metadata, and preserves source lineage for downstream proof.\n"
        "When: Used by lotus-performance to replace local or inferred component economics in "
        "stateful contribution analytics. This route does not calculate contribution, "
        "attribution, performance returns, tax advice, execution quality, best execution, or "
        "OMS acknowledgement; lotus-performance remains responsible for contribution math."
    ),
    responses={
        404: problem_response(
            "Portfolio not found",
            PERFORMANCE_COMPONENT_ECONOMICS_NOT_FOUND_EXAMPLE,
        ),
        400: problem_response(
            "Invalid performance component economics request",
            SOURCE_EVIDENCE_INVALID_REQUEST_EXAMPLE,
        ),
    },
    openapi_extra=source_data_product_openapi_extra("PerformanceComponentEconomics"),
)
async def get_performance_component_economics(
    request: PerformanceComponentEconomicsRequest,
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier whose component economics evidence should be returned.",
        examples=["PB_SG_GLOBAL_BAL_001"],
    ),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> PerformanceComponentEconomicsResponse:
    try:
        return await integration_service.get_performance_component_economics(
            portfolio_id=portfolio_id,
            request=request,
        )
    except LookupError as exc:
        _raise_source_evidence_not_found(
            source_product="PerformanceComponentEconomics",
            portfolio_id=portfolio_id,
            exc=exc,
        )
    except ValueError as exc:
        _raise_source_evidence_invalid_request(
            source_product="PerformanceComponentEconomics",
            portfolio_id=portfolio_id,
            exc=exc,
        )


@router.post(
    "/market-data/coverage",
    response_model=MarketDataCoverageWindowResponse,
    summary="Resolve DPM market-data and FX coverage",
    description=(
        "What: Return latest available price and FX coverage for the held and target DPM "
        "universe in one bounded request.\n"
        "How: Resolves latest market price and FX observations on or before as_of_date, classifies "
        "missing and stale observations, and returns supportability diagnostics for downstream "
        "source assembly.\n"
        "When: Use this endpoint when lotus-manage assembles stateful DPM market-data inputs for "
        "valuation, drift, cash conversion, and rebalance sizing. Do not use it as a historical "
        "price or FX series API."
    ),
    responses={
        422: problem_response(
            "Invalid market-data coverage request",
            {"detail": "instrument_ids must not contain duplicates"},
        ),
    },
    openapi_extra=source_data_product_openapi_extra("MarketDataCoverageWindow"),
)
async def get_market_data_coverage(
    request: MarketDataCoverageRequest = Body(...),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> MarketDataCoverageWindowResponse:
    return await integration_service.get_market_data_coverage(request)


@router.post(
    "/portfolio-manager-books/{portfolio_manager_id}/memberships",
    response_model=PortfolioManagerBookMembershipResponse,
    summary="Resolve portfolio-manager book membership",
    description=(
        "What: Return source-owned portfolio memberships for a portfolio-manager book.\n"
        "How: Resolves core portfolio master rows where `advisor_id` matches the requested "
        "portfolio_manager_id, applies as-of lifecycle, active-status, booking-center, and "
        "portfolio-type filters, and returns deterministic membership rows with supportability "
        "and lineage.\n"
        "When: Use this endpoint when lotus-manage needs automatic PM-book cohort discovery for "
        "DPM rebalance waves. Do not use it as a general staff hierarchy, entitlement, or "
        "relationship-householding API; richer relationship-book ownership remains a separate "
        "source product."
    ),
    responses={
        404: problem_response(
            "No portfolio memberships found.",
            PORTFOLIO_MANAGER_BOOK_EMPTY_EXAMPLE,
        ),
    },
    openapi_extra=source_data_product_openapi_extra("PortfolioManagerBookMembership"),
)
async def resolve_portfolio_manager_book_membership(
    request: PortfolioManagerBookMembershipRequest,
    portfolio_manager_id: str = Path(
        ...,
        description=(
            "Portfolio-manager or relationship-manager identifier backed by core portfolio "
            "master `advisor_id` in the first-wave contract."
        ),
        examples=["PM_SG_DPM_001"],
    ),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> PortfolioManagerBookMembershipResponse:
    response = await integration_service.resolve_portfolio_manager_book_membership(
        portfolio_manager_id=portfolio_manager_id,
        request=request,
    )
    members = getattr(response, "members", None)
    if members is None and isinstance(response, dict):
        members = response.get("members", [])
    if not members:
        _raise_integration_source_not_found(
            source_product="PortfolioManagerBookMembership",
            detail=PORTFOLIO_MANAGER_BOOK_EMPTY_DETAIL,
            metadata={
                "portfolio_manager_id": portfolio_manager_id,
                "reason": "empty_result",
            },
        )
    return response


@router.post(
    "/model-portfolios/{model_portfolio_id}/affected-mandates",
    response_model=CioModelChangeAffectedCohortResponse,
    summary="Resolve CIO model-change affected mandate cohort",
    description=(
        "What: Return source-owned affected discretionary mandates for an approved CIO model "
        "portfolio version.\n"
        "How: Resolves the approved model definition for the as-of date, then selects effective "
        "portfolio mandate bindings for the model, preserving booking-center filters, active "
        "discretionary authority, supportability, event identity, and source lineage.\n"
        "When: Use this endpoint when lotus-manage needs automatic CIO_MODEL_CHANGE wave "
        "discovery. Do not infer affected cohorts inside consumers from a model id alone."
    ),
    responses={
        404: problem_response(
            "No affected mandates found.",
            CIO_MODEL_CHANGE_AFFECTED_COHORT_EMPTY_EXAMPLE,
        ),
    },
    openapi_extra=source_data_product_openapi_extra("CioModelChangeAffectedCohort"),
)
async def resolve_cio_model_change_affected_cohort(
    request: CioModelChangeAffectedCohortRequest,
    model_portfolio_id: str = Path(
        ...,
        description="Approved model portfolio identifier whose affected mandate cohort is needed.",
        examples=["MODEL_PB_SG_GLOBAL_BAL_DPM"],
    ),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> CioModelChangeAffectedCohortResponse:
    response = await integration_service.resolve_cio_model_change_affected_cohort(
        model_portfolio_id=model_portfolio_id,
        request=request,
    )
    if response is None:
        _raise_integration_source_not_found(
            source_product="CioModelChangeAffectedCohort",
            detail="Approved model portfolio definition was not found for model_portfolio_id.",
            metadata={
                "model_portfolio_id": model_portfolio_id,
                "reason": "not_found",
            },
        )
    affected_mandates = getattr(response, "affected_mandates", None)
    if affected_mandates is None and isinstance(response, dict):
        affected_mandates = response.get("affected_mandates", [])
    if not affected_mandates:
        _raise_integration_source_not_found(
            source_product="CioModelChangeAffectedCohort",
            detail=CIO_MODEL_CHANGE_AFFECTED_COHORT_EMPTY_DETAIL,
            metadata={
                "model_portfolio_id": model_portfolio_id,
                "reason": "empty_result",
            },
        )
    return response


@router.post(
    "/dpm/portfolio-universe/candidates",
    response_model=DpmPortfolioUniverseCandidateResponse,
    summary="Resolve DPM portfolio-universe candidates",
    description=(
        "What: Return source-owned DPM portfolio-universe candidates from effective "
        "discretionary mandate bindings.\n"
        "How: Applies as-of, booking-center, model-portfolio, active-authority, and deterministic "
        "paging controls against Core-owned mandate binding records, then returns candidate rows "
        "with supportability, continuation metadata, and lineage.\n"
        "When: Use this endpoint when lotus-manage needs source-owned DPM universe discovery "
        "before campaign or wave composition. Do not use it as a client householding, suitability, "
        "portfolio-manager ranking, execution, or external workflow API."
    ),
    responses={
        404: problem_response(
            "No DPM portfolio-universe candidates found.",
            DPM_PORTFOLIO_UNIVERSE_EMPTY_EXAMPLE,
        ),
        422: problem_or_validation_response(
            "Invalid DPM portfolio-universe request",
            DPM_PORTFOLIO_UNIVERSE_INVALID_REQUEST_EXAMPLE,
        ),
    },
    openapi_extra=source_data_product_openapi_extra("DpmPortfolioUniverseCandidate"),
)
async def resolve_dpm_portfolio_universe_candidates(
    request: DpmPortfolioUniverseCandidateRequest,
    integration_service: IntegrationService = Depends(get_integration_service),
) -> DpmPortfolioUniverseCandidateResponse:
    try:
        response = await integration_service.resolve_dpm_portfolio_universe_candidates(
            request=request,
        )
    except ValueError as exc:
        _raise_integration_source_invalid_request(
            source_product="DpmPortfolioUniverseCandidate",
            detail=DPM_PORTFOLIO_UNIVERSE_INVALID_REQUEST_DETAIL,
            exc=exc,
        )
    candidates = getattr(response, "candidates", None)
    if candidates is None and isinstance(response, dict):
        candidates = response.get("candidates", [])
    if not candidates:
        _raise_integration_source_not_found(
            source_product="DpmPortfolioUniverseCandidate",
            detail=DPM_PORTFOLIO_UNIVERSE_EMPTY_DETAIL,
            metadata={"reason": "empty_result"},
        )
    return response


@router.post(
    "/portfolios/{portfolio_id}/dpm-source-readiness",
    response_model=DpmSourceReadinessResponse,
    summary="Evaluate DPM source-family readiness",
    description=(
        "What: Return a control-plane readiness summary across the governed source families "
        "required before lotus-manage may promote stateful discretionary mandate execution.\n"
        "How: Evaluates mandate binding, model targets, instrument eligibility, portfolio tax "
        "lots, and market-data/FX coverage through the product-specific core source APIs, then "
        "returns bounded source-family states and reason codes. It does not return a composed "
        "execution context or duplicate the detailed source products.\n"
        "When: Use this endpoint as the promotion gate for lotus-manage stateful `portfolio_id` "
        "execution and as the operator supportability summary for DPM source-data incidents. Do "
        "not use it as an all-in-one data feed; call the individual source products for data."
    ),
    responses={
        422: problem_response(
            "Invalid DPM source-readiness request",
            {"detail": "instrument_ids must not contain duplicates"},
        ),
    },
    openapi_extra=source_data_product_openapi_extra("DpmSourceReadiness"),
)
async def get_dpm_source_readiness(
    request: DpmSourceReadinessRequest,
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier whose DPM source-family readiness is evaluated.",
        examples=["PB_SG_GLOBAL_BAL_001"],
    ),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> DpmSourceReadinessResponse:
    return await integration_service.get_dpm_source_readiness(
        portfolio_id=portfolio_id,
        request=request,
    )


@router.post(
    "/portfolios/{portfolio_id}/benchmark-assignment",
    response_model=BenchmarkAssignmentResponse,
    responses={
        status.HTTP_404_NOT_FOUND: problem_response(
            "No effective benchmark assignment found.",
            BENCHMARK_ASSIGNMENT_NOT_FOUND_EXAMPLE,
        ),
    },
    summary="Resolve effective portfolio benchmark assignment",
    description=(
        "What: Resolve benchmark assignment for a portfolio as-of a point-in-time date.\n"
        "How: Applies effective-dating and assignment version ordering to return "
        "deterministic match. Resolution is keyed by portfolio_id and as_of_date; "
        "request reporting_currency and policy_context are caller-context fields and do "
        "not change assignment selection in the current implementation.\n"
        "When: Used by lotus-performance benchmark-aware analytics, lotus-gateway workspace "
        "composition flows, and reporting workflows that need governed benchmark context "
        "before downstream benchmark math or evidence generation."
    ),
    openapi_extra=source_data_product_openapi_extra("BenchmarkAssignment"),
)
async def resolve_portfolio_benchmark_assignment(
    request: BenchmarkAssignmentRequest,
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier whose effective benchmark assignment is requested.",
        examples=["PORT-INT-001"],
    ),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> BenchmarkAssignmentResponse:
    response = cast(
        BenchmarkAssignmentResponse | None,
        await integration_service.resolve_benchmark_assignment(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
        ),
    )
    if response is None:
        _raise_integration_source_not_found(
            source_product="BenchmarkAssignment",
            detail=BENCHMARK_ASSIGNMENT_NOT_FOUND_DETAIL,
            metadata={
                "portfolio_id": portfolio_id,
                "reason": "not_found",
            },
        )
    return response


@router.post(
    "/model-portfolios/{model_portfolio_id}/targets",
    response_model=ModelPortfolioTargetResponse,
    responses={
        status.HTTP_404_NOT_FOUND: problem_response(
            "No approved model portfolio target found.",
            MODEL_PORTFOLIO_TARGET_NOT_FOUND_EXAMPLE,
        ),
    },
    summary="Resolve approved DPM model portfolio targets",
    description=(
        "What: Return the approved effective-dated model portfolio target weights and "
        "instrument bands required by discretionary mandate portfolio management.\n"
        "How: Resolves the latest approved model version for `model_portfolio_id` and "
        "`as_of_date`, filters inactive targets by default, returns deterministic "
        "instrument ordering, and includes source-data runtime metadata, supportability, "
        "and lineage.\n"
        "When: Use this endpoint when lotus-manage needs governed target allocation input "
        "for stateful DPM analysis, simulation, or rebalance execution. Do not use it as "
        "a general advisory proposal simulator or as a replacement for portfolio holdings."
    ),
    openapi_extra=source_data_product_openapi_extra("DpmModelPortfolioTarget"),
)
async def resolve_model_portfolio_targets(
    request: ModelPortfolioTargetRequest,
    model_portfolio_id: str = Path(
        ...,
        description="Canonical model portfolio identifier whose targets are requested.",
        examples=["MODEL_SG_BALANCED_DPM"],
    ),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> ModelPortfolioTargetResponse:
    response = cast(
        ModelPortfolioTargetResponse | None,
        await integration_service.resolve_model_portfolio_targets(
            model_portfolio_id=model_portfolio_id,
            request=request,
        ),
    )
    if response is None:
        _raise_integration_source_not_found(
            source_product="DpmModelPortfolioTarget",
            detail=MODEL_PORTFOLIO_TARGET_NOT_FOUND_DETAIL,
            metadata={
                "model_portfolio_id": model_portfolio_id,
                "reason": "not_found",
            },
        )
    return response


@router.post(
    "/portfolios/{portfolio_id}/mandate-binding",
    response_model=DiscretionaryMandateBindingResponse,
    responses={
        status.HTTP_404_NOT_FOUND: problem_response(
            "No effective discretionary mandate binding found.",
            MANDATE_BINDING_NOT_FOUND_EXAMPLE,
        ),
    },
    summary="Resolve effective DPM mandate binding",
    description=(
        "What: Return the effective discretionary mandate binding that connects a portfolio "
        "to its mandate objective, model portfolio, policy pack, jurisdiction, booking center, "
        "authority status, review cadence, review dates, and rebalance constraints.\n"
        "How: Applies effective-date, optional mandate, optional booking-center, and binding "
        "version ordering to return one deterministic source record with source-data runtime "
        "metadata, supportability, and lineage.\n"
        "When: Use this endpoint before lotus-manage stateful DPM source assembly so model "
        "target sourcing, policy checks, tax-aware mode, and settlement-aware mode are driven "
        "by governed core source data. Do not use it for advisory proposal simulation or as a "
        "general benchmark assignment replacement."
    ),
    openapi_extra=source_data_product_openapi_extra("DiscretionaryMandateBinding"),
)
async def resolve_discretionary_mandate_binding(
    request: DiscretionaryMandateBindingRequest,
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier whose discretionary mandate binding is requested.",
        examples=["PB_SG_GLOBAL_BAL_001"],
    ),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> DiscretionaryMandateBindingResponse:
    response = cast(
        DiscretionaryMandateBindingResponse | None,
        await integration_service.resolve_discretionary_mandate_binding(
            portfolio_id=portfolio_id,
            request=request,
        ),
    )
    if response is None:
        _raise_integration_source_not_found(
            source_product="DiscretionaryMandateBinding",
            detail=MANDATE_BINDING_NOT_FOUND_DETAIL,
            metadata={
                "portfolio_id": portfolio_id,
                "reason": "not_found",
            },
        )
    return response


@router.post(
    "/portfolios/{portfolio_id}/client-restriction-profile",
    response_model=ClientRestrictionProfileResponse,
    responses={
        status.HTTP_404_NOT_FOUND: problem_response(
            "No effective discretionary mandate binding found.",
            CLIENT_RESTRICTION_PROFILE_NOT_FOUND_EXAMPLE,
        ),
    },
    summary="Resolve effective client restriction profile",
    description=(
        "What: Return effective source-owned client and mandate restriction records for a "
        "portfolio.\n"
        "How: Resolves the effective discretionary mandate binding first, then selects active "
        "client restriction profile records by portfolio, client, mandate, and as-of date with "
        "deterministic version ordering.\n"
        "When: Use this endpoint when lotus-manage needs restriction-aware DPM construction "
        "evidence. The response publishes bounded restriction codes and scopes only; sensitive "
        "free-text suitability rationale remains out of this downstream source product."
    ),
    openapi_extra=source_data_product_openapi_extra("ClientRestrictionProfile"),
)
async def get_client_restriction_profile(
    request: ClientRestrictionProfileRequest,
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier whose client restriction profile is requested.",
        examples=["PB_SG_GLOBAL_BAL_001"],
    ),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> ClientRestrictionProfileResponse:
    response = cast(
        ClientRestrictionProfileResponse | None,
        await integration_service.get_client_restriction_profile(
            portfolio_id=portfolio_id,
            request=request,
        ),
    )
    if response is None:
        _raise_mandate_scoped_source_not_found(
            source_product="ClientRestrictionProfile",
            portfolio_id=portfolio_id,
        )
    return response


@router.post(
    "/portfolios/{portfolio_id}/sustainability-preference-profile",
    response_model=SustainabilityPreferenceProfileResponse,
    responses={
        status.HTTP_404_NOT_FOUND: problem_response(
            "No effective discretionary mandate binding found.",
            SUSTAINABILITY_PREFERENCE_PROFILE_NOT_FOUND_EXAMPLE,
        ),
    },
    summary="Resolve effective sustainability preference profile",
    description=(
        "What: Return effective source-owned sustainability preference records for a portfolio.\n"
        "How: Resolves the effective discretionary mandate binding first, then selects active "
        "sustainability preference profile records by portfolio, client, mandate, framework, "
        "preference code, and as-of date with deterministic version ordering.\n"
        "When: Use this endpoint when lotus-manage needs sustainability-aware DPM construction "
        "evidence. The response publishes bounded framework, preference, exclusion, positive "
        "tilt, and allocation fields; downstream services must not infer unstated client "
        "preferences."
    ),
    openapi_extra=source_data_product_openapi_extra("SustainabilityPreferenceProfile"),
)
async def get_sustainability_preference_profile(
    request: SustainabilityPreferenceProfileRequest,
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier whose sustainability preference profile is requested.",
        examples=["PB_SG_GLOBAL_BAL_001"],
    ),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> SustainabilityPreferenceProfileResponse:
    response = cast(
        SustainabilityPreferenceProfileResponse | None,
        await integration_service.get_sustainability_preference_profile(
            portfolio_id=portfolio_id,
            request=request,
        ),
    )
    if response is None:
        _raise_mandate_scoped_source_not_found(
            source_product="SustainabilityPreferenceProfile",
            portfolio_id=portfolio_id,
        )
    return response


@router.post(
    "/portfolios/{portfolio_id}/client-tax-profile",
    response_model=ClientTaxProfileResponse,
    responses={
        status.HTTP_404_NOT_FOUND: problem_response(
            "No effective discretionary mandate binding found.",
            CLIENT_TAX_PROFILE_NOT_FOUND_EXAMPLE,
        ),
    },
    summary="Resolve effective client tax profile",
    description=(
        "What: Return effective source-owned client tax profile records for a portfolio.\n"
        "How: Resolves the effective discretionary mandate binding first, then selects active "
        "client tax profile records by portfolio, client, mandate, and as-of date with "
        "deterministic version ordering.\n"
        "When: Use this endpoint when lotus-manage needs bounded tax-reference evidence for "
        "DPM governance. The response publishes source-owned reference fields only; it does "
        "not provide tax advice, after-tax optimization, tax-loss harvesting suitability, or "
        "jurisdiction-specific recommendations."
    ),
    openapi_extra=source_data_product_openapi_extra("ClientTaxProfile"),
)
async def get_client_tax_profile(
    request: ClientTaxProfileRequest,
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier whose client tax profile is requested.",
        examples=["PB_SG_GLOBAL_BAL_001"],
    ),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> ClientTaxProfileResponse:
    response = cast(
        ClientTaxProfileResponse | None,
        await integration_service.get_client_tax_profile(
            portfolio_id=portfolio_id,
            request=request,
        ),
    )
    if response is None:
        _raise_mandate_scoped_source_not_found(
            source_product="ClientTaxProfile",
            portfolio_id=portfolio_id,
        )
    return response


@router.post(
    "/portfolios/{portfolio_id}/client-tax-rule-set",
    response_model=ClientTaxRuleSetResponse,
    responses={
        status.HTTP_404_NOT_FOUND: problem_response(
            "No effective discretionary mandate binding found.",
            CLIENT_TAX_RULE_SET_NOT_FOUND_EXAMPLE,
        ),
    },
    summary="Resolve effective client tax rule set",
    description=(
        "What: Return effective source-owned client tax rule references for a portfolio.\n"
        "How: Resolves the effective discretionary mandate binding first, then selects active "
        "client tax rule-set records by portfolio, client, mandate, jurisdiction, rule code, "
        "and as-of date with deterministic version ordering.\n"
        "When: Use this endpoint when lotus-manage needs bounded tax-rule reference evidence "
        "for DPM governance. The response does not approve client tax outcomes, recommend "
        "tax-loss harvesting, or replace bank-owned tax systems."
    ),
    openapi_extra=source_data_product_openapi_extra("ClientTaxRuleSet"),
)
async def get_client_tax_rule_set(
    request: ClientTaxRuleSetRequest,
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier whose client tax rule set is requested.",
        examples=["PB_SG_GLOBAL_BAL_001"],
    ),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> ClientTaxRuleSetResponse:
    response = cast(
        ClientTaxRuleSetResponse | None,
        await integration_service.get_client_tax_rule_set(
            portfolio_id=portfolio_id,
            request=request,
        ),
    )
    if response is None:
        _raise_mandate_scoped_source_not_found(
            source_product="ClientTaxRuleSet",
            portfolio_id=portfolio_id,
        )
    return response


@router.post(
    "/portfolios/{portfolio_id}/client-income-needs-schedule",
    response_model=ClientIncomeNeedsScheduleResponse,
    responses={
        status.HTTP_404_NOT_FOUND: problem_response(
            "No effective discretionary mandate binding found.",
            CLIENT_INCOME_NEEDS_SCHEDULE_NOT_FOUND_EXAMPLE,
        ),
    },
    summary="Resolve effective client income-needs schedule",
    description=(
        "What: Return effective source-owned client income-needs schedule records for a "
        "portfolio.\n"
        "How: Resolves the effective discretionary mandate binding first, then selects active "
        "income-needs records by portfolio, client, mandate, and as-of date with deterministic "
        "version ordering.\n"
        "When: Use this endpoint when lotus-manage needs bounded cashflow-needs evidence for "
        "DPM construction and monitoring. The response publishes source-owned reference fields "
        "only; it does not provide financial-planning advice, client liability planning, "
        "suitability approval, or funding recommendations."
    ),
    openapi_extra=source_data_product_openapi_extra("ClientIncomeNeedsSchedule"),
)
async def get_client_income_needs_schedule(
    request: ClientIncomeNeedsScheduleRequest,
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier whose client income-needs schedule is requested.",
        examples=["PB_SG_GLOBAL_BAL_001"],
    ),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> ClientIncomeNeedsScheduleResponse:
    response = cast(
        ClientIncomeNeedsScheduleResponse | None,
        await integration_service.get_client_income_needs_schedule(
            portfolio_id=portfolio_id,
            request=request,
        ),
    )
    if response is None:
        _raise_mandate_scoped_source_not_found(
            source_product="ClientIncomeNeedsSchedule",
            portfolio_id=portfolio_id,
        )
    return response


@router.post(
    "/portfolios/{portfolio_id}/liquidity-reserve-requirement",
    response_model=LiquidityReserveRequirementResponse,
    responses={
        status.HTTP_404_NOT_FOUND: problem_response(
            "No effective discretionary mandate binding found.",
            LIQUIDITY_RESERVE_REQUIREMENT_NOT_FOUND_EXAMPLE,
        ),
    },
    summary="Resolve effective liquidity reserve requirements",
    description=(
        "What: Return effective source-owned liquidity reserve requirement records for a "
        "portfolio.\n"
        "How: Resolves the effective discretionary mandate binding first, then selects active "
        "reserve requirements by portfolio, client, mandate, and as-of date with deterministic "
        "version ordering.\n"
        "When: Use this endpoint when lotus-manage needs bounded liquidity-reserve evidence "
        "for DPM construction and supportability checks. The response does not approve a cash "
        "reserve recommendation, provide financial-planning advice, approve suitability, or "
        "replace bank-owned treasury and liquidity policy systems."
    ),
    openapi_extra=source_data_product_openapi_extra("LiquidityReserveRequirement"),
)
async def get_liquidity_reserve_requirement(
    request: LiquidityReserveRequirementRequest,
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier whose liquidity reserve requirement is requested.",
        examples=["PB_SG_GLOBAL_BAL_001"],
    ),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> LiquidityReserveRequirementResponse:
    response = cast(
        LiquidityReserveRequirementResponse | None,
        await integration_service.get_liquidity_reserve_requirement(
            portfolio_id=portfolio_id,
            request=request,
        ),
    )
    if response is None:
        _raise_mandate_scoped_source_not_found(
            source_product="LiquidityReserveRequirement",
            portfolio_id=portfolio_id,
        )
    return response


@router.post(
    "/portfolios/{portfolio_id}/planned-withdrawal-schedule",
    response_model=PlannedWithdrawalScheduleResponse,
    responses={
        status.HTTP_404_NOT_FOUND: problem_response(
            "No effective discretionary mandate binding found.",
            PLANNED_WITHDRAWAL_SCHEDULE_NOT_FOUND_EXAMPLE,
        ),
    },
    summary="Resolve planned withdrawal schedules",
    description=(
        "What: Return source-owned planned withdrawal records for a portfolio over a requested "
        "forward horizon.\n"
        "How: Resolves the effective discretionary mandate binding first, then selects active "
        "withdrawal records by portfolio, client, mandate, and scheduled date with "
        "deterministic ordering.\n"
        "When: Use this endpoint when lotus-manage needs bounded planned-withdrawal evidence "
        "for DPM liquidity checks. The response is not a cashflow forecast, financial-planning "
        "advice, suitability approval, funding recommendation, or OMS acknowledgement."
    ),
    openapi_extra=source_data_product_openapi_extra("PlannedWithdrawalSchedule"),
)
async def get_planned_withdrawal_schedule(
    request: PlannedWithdrawalScheduleRequest,
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier whose planned withdrawal schedule is requested.",
        examples=["PB_SG_GLOBAL_BAL_001"],
    ),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> PlannedWithdrawalScheduleResponse:
    response = cast(
        PlannedWithdrawalScheduleResponse | None,
        await integration_service.get_planned_withdrawal_schedule(
            portfolio_id=portfolio_id,
            request=request,
        ),
    )
    if response is None:
        _raise_mandate_scoped_source_not_found(
            source_product="PlannedWithdrawalSchedule",
            portfolio_id=portfolio_id,
        )
    return response


@router.post(
    "/portfolios/{portfolio_id}/external-hedge-policy",
    response_model=ExternalHedgePolicyResponse,
    responses={
        status.HTTP_404_NOT_FOUND: problem_response(
            "No effective discretionary mandate binding found.",
            EXTERNAL_HEDGE_POLICY_NOT_FOUND_EXAMPLE,
        ),
    },
    summary="Resolve external treasury hedge policy posture",
    description=(
        "What: Return the source-owner posture for external treasury hedge policy evidence "
        "for a DPM portfolio.\n"
        "How: Resolves the effective discretionary mandate binding for portfolio identity, "
        "then returns a fail-closed unavailable posture until bank-owned external treasury "
        "policy feeds are ingested and certified.\n"
        "When: Use this endpoint when lotus-manage or gateway needs bounded RFC39-WTBD-008 "
        "hedge-policy supportability. The response does not approve hedge policy, provide "
        "hedge advice, issue treasury instructions, choose counterparties, generate orders, "
        "declare best execution, acknowledge OMS execution, or claim fills, settlement, or "
        "autonomous treasury action."
    ),
    openapi_extra=source_data_product_openapi_extra("ExternalHedgePolicy"),
)
async def get_external_hedge_policy(
    request: ExternalHedgePolicyRequest,
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier whose external hedge policy is requested.",
        examples=["PB_SG_GLOBAL_BAL_001"],
    ),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> ExternalHedgePolicyResponse:
    response = cast(
        ExternalHedgePolicyResponse | None,
        await integration_service.get_external_hedge_policy(
            portfolio_id=portfolio_id,
            request=request,
        ),
    )
    if response is None:
        _raise_mandate_scoped_source_not_found(
            source_product="ExternalHedgePolicy",
            portfolio_id=portfolio_id,
        )
    return response


@router.post(
    "/portfolios/{portfolio_id}/external-hedge-execution-readiness",
    response_model=ExternalHedgeExecutionReadinessResponse,
    responses={
        status.HTTP_404_NOT_FOUND: problem_response(
            "No effective discretionary mandate binding found.",
            EXTERNAL_HEDGE_EXECUTION_READINESS_NOT_FOUND_EXAMPLE,
        ),
    },
    summary="Resolve external treasury hedge execution readiness posture",
    description=(
        "What: Return the source-owner posture for external treasury hedge execution "
        "readiness for a DPM portfolio.\n"
        "How: Resolves the effective discretionary mandate binding for portfolio identity, "
        "then returns a fail-closed unavailable posture until bank-owned external treasury "
        "source products are ingested and certified.\n"
        "When: Use this endpoint when lotus-manage or gateway needs a bounded RFC39-WTBD-008 "
        "source signal for currency-overlay supportability. The response does not provide "
        "hedge advice, forward pricing, counterparty selection, best execution, OMS "
        "acknowledgement, fills, settlement, or autonomous treasury action."
    ),
    openapi_extra=source_data_product_openapi_extra("ExternalHedgeExecutionReadiness"),
)
async def get_external_hedge_execution_readiness(
    request: ExternalHedgeExecutionReadinessRequest,
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier whose external treasury readiness is requested.",
        examples=["PB_SG_GLOBAL_BAL_001"],
    ),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> ExternalHedgeExecutionReadinessResponse:
    response = cast(
        ExternalHedgeExecutionReadinessResponse | None,
        await integration_service.get_external_hedge_execution_readiness(
            portfolio_id=portfolio_id,
            request=request,
        ),
    )
    if response is None:
        _raise_mandate_scoped_source_not_found(
            source_product="ExternalHedgeExecutionReadiness",
            portfolio_id=portfolio_id,
        )
    return response


@router.post(
    "/portfolios/{portfolio_id}/external-order-execution-acknowledgement",
    response_model=ExternalOrderExecutionAcknowledgementResponse,
    responses={
        status.HTTP_404_NOT_FOUND: problem_response(
            "No effective discretionary mandate binding found.",
            EXTERNAL_ORDER_EXECUTION_ACKNOWLEDGEMENT_NOT_FOUND_EXAMPLE,
        ),
    },
    summary="Resolve external OMS order execution acknowledgement posture",
    description=(
        "What: Return the source-owner posture for external OMS order-execution "
        "acknowledgement evidence for a DPM portfolio.\n"
        "How: Resolves the effective discretionary mandate binding for portfolio identity, "
        "then returns a fail-closed unavailable posture until bank-owned external OMS "
        "acknowledgement feeds are ingested and certified.\n"
        "When: Use this endpoint when lotus-manage or gateway needs bounded RFC42-WTBD "
        "execution acknowledgement supportability. The response does not create orders, "
        "route venues, declare best execution, acknowledge OMS execution, certify fills, "
        "confirm settlement, or perform autonomous execution action."
    ),
    openapi_extra=source_data_product_openapi_extra("ExternalOrderExecutionAcknowledgement"),
)
async def get_external_order_execution_acknowledgement(
    request: ExternalOrderExecutionAcknowledgementRequest,
    portfolio_id: str = Path(
        ...,
        description=(
            "Portfolio identifier whose external OMS acknowledgement posture is requested."
        ),
        examples=["PB_SG_GLOBAL_BAL_001"],
    ),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> ExternalOrderExecutionAcknowledgementResponse:
    response = cast(
        ExternalOrderExecutionAcknowledgementResponse | None,
        await integration_service.get_external_order_execution_acknowledgement(
            portfolio_id=portfolio_id,
            request=request,
        ),
    )
    if response is None:
        _raise_mandate_scoped_source_not_found(
            source_product="ExternalOrderExecutionAcknowledgement",
            portfolio_id=portfolio_id,
        )
    return response


@router.post(
    "/portfolios/{portfolio_id}/external-currency-exposure",
    response_model=ExternalCurrencyExposureResponse,
    responses={
        status.HTTP_404_NOT_FOUND: problem_response(
            "No effective discretionary mandate binding found.",
            EXTERNAL_CURRENCY_EXPOSURE_NOT_FOUND_EXAMPLE,
        ),
    },
    summary="Resolve external treasury currency exposure posture",
    description=(
        "What: Return the source-owner posture for external treasury currency exposure "
        "evidence for a DPM portfolio.\n"
        "How: Resolves the effective discretionary mandate binding for portfolio identity, "
        "then returns a fail-closed unavailable posture until bank-owned external treasury "
        "exposure feeds are ingested and certified.\n"
        "When: Use this endpoint when lotus-manage or gateway needs a bounded RFC39-WTBD-008 "
        "source signal for currency-overlay supportability. The response does not calculate "
        "FX attribution, provide hedge advice, issue treasury instructions, declare execution "
        "readiness, acknowledge OMS execution, or claim fills, settlement, or autonomous "
        "treasury action."
    ),
    openapi_extra=source_data_product_openapi_extra("ExternalCurrencyExposure"),
)
async def get_external_currency_exposure(
    request: ExternalCurrencyExposureRequest,
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier whose external currency exposure is requested.",
        examples=["PB_SG_GLOBAL_BAL_001"],
    ),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> ExternalCurrencyExposureResponse:
    response = cast(
        ExternalCurrencyExposureResponse | None,
        await integration_service.get_external_currency_exposure(
            portfolio_id=portfolio_id,
            request=request,
        ),
    )
    if response is None:
        _raise_mandate_scoped_source_not_found(
            source_product="ExternalCurrencyExposure",
            portfolio_id=portfolio_id,
        )
    return response


@router.post(
    "/portfolios/{portfolio_id}/external-eligible-hedge-instruments",
    response_model=ExternalEligibleHedgeInstrumentResponse,
    responses={
        status.HTTP_404_NOT_FOUND: problem_response(
            "No effective discretionary mandate binding found.",
            EXTERNAL_ELIGIBLE_HEDGE_INSTRUMENT_NOT_FOUND_EXAMPLE,
        ),
    },
    summary="Resolve external treasury eligible hedge instrument posture",
    description=(
        "What: Return the source-owner posture for external treasury eligible hedge "
        "instrument evidence for a DPM portfolio.\n"
        "How: Resolves the effective discretionary mandate binding for portfolio identity, "
        "then returns a fail-closed unavailable posture until bank-owned external treasury "
        "instrument eligibility feeds are ingested and certified.\n"
        "When: Use this endpoint when lotus-manage or gateway needs bounded RFC39-WTBD-008 "
        "eligible hedge instrument supportability. The response does not perform suitability "
        "approval, recommend hedge products, choose counterparties, issue treasury "
        "instructions, generate orders, declare best execution, acknowledge OMS execution, "
        "or claim fills, settlement, or autonomous treasury action."
    ),
    openapi_extra=source_data_product_openapi_extra("ExternalEligibleHedgeInstrument"),
)
async def get_external_eligible_hedge_instruments(
    request: ExternalEligibleHedgeInstrumentRequest,
    portfolio_id: str = Path(
        ...,
        description=(
            "Portfolio identifier whose external eligible hedge instruments are requested."
        ),
        examples=["PB_SG_GLOBAL_BAL_001"],
    ),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> ExternalEligibleHedgeInstrumentResponse:
    response = cast(
        ExternalEligibleHedgeInstrumentResponse | None,
        await integration_service.get_external_eligible_hedge_instruments(
            portfolio_id=portfolio_id,
            request=request,
        ),
    )
    if response is None:
        _raise_mandate_scoped_source_not_found(
            source_product="ExternalEligibleHedgeInstrument",
            portfolio_id=portfolio_id,
        )
    return response


@router.post(
    "/market-data/external-fx-forward-curve",
    response_model=ExternalFXForwardCurveResponse,
    summary="Resolve external treasury FX forward curve posture",
    description=(
        "What: Return the source-owner posture for external treasury FX forward curve "
        "evidence needed by DPM currency-overlay workflows.\n"
        "How: Echoes the requested as-of date, reporting currency, currency pairs, and tenors, "
        "then returns a fail-closed unavailable posture until bank-owned external treasury "
        "curve feeds are ingested and certified.\n"
        "When: Use this endpoint when lotus-manage or gateway needs bounded "
        "RFC39-WTBD-008 forward-curve supportability. The response does not price forwards, "
        "perform FX valuation methodology, provide hedge advice, issue treasury instructions, "
        "select counterparties, generate orders, declare best execution, route venues, "
        "acknowledge OMS execution, or claim fills, settlement, or autonomous treasury action."
    ),
    openapi_extra=source_data_product_openapi_extra("ExternalFXForwardCurve"),
)
async def get_external_fx_forward_curve(
    request: ExternalFXForwardCurveRequest,
    integration_service: IntegrationService = Depends(get_integration_service),
) -> ExternalFXForwardCurveResponse:
    return await integration_service.get_external_fx_forward_curve(request=request)


@router.post(
    "/benchmarks/{benchmark_id}/composition-window",
    response_model=BenchmarkCompositionWindowResponse,
    responses={
        status.HTTP_404_NOT_FOUND: problem_response(
            "No overlapping benchmark definition found.",
            BENCHMARK_COMPOSITION_WINDOW_NOT_FOUND_EXAMPLE,
        ),
        status.HTTP_409_CONFLICT: problem_response(
            "Benchmark definition changed incompatibly inside the requested window.",
            BENCHMARK_COMPOSITION_WINDOW_CONFLICT_EXAMPLE,
        ),
    },
    summary="Fetch overlapping benchmark composition segments",
    description=(
        "What: Return all effective benchmark composition segments overlapping a "
        "requested window.\n"
        "How: Resolves overlapping benchmark definition and composition records with "
        "deterministic ordering and without daily-expanding weights.\n"
        "When: Used by lotus-performance and other downstream consumers to calculate benchmark "
        "returns across rebalance windows. This is the strategic cross-rebalance source "
        "contract; single-date benchmark definition reads are not a substitute for "
        "long-window benchmark math."
    ),
    openapi_extra=source_data_product_openapi_extra("BenchmarkConstituentWindow"),
)
async def fetch_benchmark_composition_window(
    request: BenchmarkCompositionWindowRequest,
    benchmark_id: str = Path(
        ...,
        description="Benchmark identifier for the requested composition window contract.",
        examples=["BENCH-SP500-TR"],
    ),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> BenchmarkCompositionWindowResponse:
    try:
        response = cast(
            BenchmarkCompositionWindowResponse | None,
            await integration_service.get_benchmark_composition_window(
                benchmark_id=benchmark_id,
                request=request,
            ),
        )
    except ValueError as exc:
        _raise_integration_source_conflict(
            source_product="BenchmarkConstituentWindow",
            detail=BENCHMARK_COMPOSITION_WINDOW_CONFLICT_DETAIL,
            exc=exc,
            metadata={"benchmark_id": benchmark_id},
        )
    if response is None:
        _raise_integration_source_not_found(
            source_product="BenchmarkConstituentWindow",
            detail=BENCHMARK_COMPOSITION_WINDOW_NOT_FOUND_DETAIL,
            metadata={"benchmark_id": benchmark_id, "reason": "not_found"},
        )
    return response


@router.post(
    "/benchmarks/{benchmark_id}/definition",
    response_model=BenchmarkDefinitionResponse,
    responses={
        status.HTTP_404_NOT_FOUND: problem_response(
            "No effective benchmark definition found.",
            BENCHMARK_DEFINITION_NOT_FOUND_EXAMPLE,
        )
    },
    summary="Fetch effective benchmark definition",
    description=(
        "What: Return effective benchmark definition for an as-of date.\n"
        "How: Resolves benchmark master fields and composition records with effective dating.\n"
        "When: Used directly by lotus-performance stateful benchmark sourcing and other "
        "downstream consumers that need point-in-time benchmark reference context before "
        "targeted composition-window, market-series, or benchmark-aware reporting workflows. "
        "This is point-in-time reference context, not the strategic cross-window benchmark "
        "calculation contract."
    ),
)
async def fetch_benchmark_definition(
    request: BenchmarkDefinitionRequest,
    benchmark_id: str = Path(
        ...,
        description="Benchmark identifier for the requested benchmark definition.",
        examples=["BENCH-SP500-TR"],
    ),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> BenchmarkDefinitionResponse:
    response = cast(
        BenchmarkDefinitionResponse | None,
        await integration_service.get_benchmark_definition(benchmark_id, request.as_of_date),
    )
    if response is None:
        _raise_integration_source_not_found(
            source_product="BenchmarkDefinition",
            detail=BENCHMARK_DEFINITION_NOT_FOUND_DETAIL,
            metadata={"benchmark_id": benchmark_id, "reason": "not_found"},
        )
    return response


@router.post(
    "/benchmarks/catalog",
    response_model=BenchmarkCatalogResponse,
    summary="Fetch benchmark master catalog",
    description=(
        "What: Return benchmark master records effective on a requested date.\n"
        "How: Applies optional filters and effective dating in query service.\n"
        "When: Used directly by lotus-gateway workspace benchmark selection flows and other "
        "downstream discovery workflows to find valid benchmark references before targeted "
        "benchmark assignment, definition, market-series, or benchmark-return retrieval. "
        "Prefer the targeted routes once a concrete benchmark identifier is known."
    ),
)
async def fetch_benchmark_catalog(
    request: BenchmarkCatalogRequest,
    integration_service: IntegrationService = Depends(get_integration_service),
) -> BenchmarkCatalogResponse:
    return cast(
        BenchmarkCatalogResponse,
        await integration_service.list_benchmark_catalog(
            as_of_date=request.as_of_date,
            benchmark_type=request.benchmark_type,
            benchmark_currency=request.benchmark_currency,
            benchmark_status=request.benchmark_status,
        ),
    )


@router.post(
    "/indices/catalog",
    response_model=IndexCatalogResponse,
    summary="Fetch index master catalog",
    description=(
        "What: Return index master records effective on a requested date.\n"
        "How: Applies optional targeted index_ids filters, broader attribute filters, and "
        "effective dating in query service.\n"
        "When: Used directly by lotus-performance benchmark exposure and attribution sourcing "
        "flows to discover canonical index metadata and governed classification labels. "
        "Benchmark component indices can publish broad-market sector labels such as "
        "`broad_market_equity` or `broad_market_fixed_income` for exposure grouping. When a "
        "downstream caller already knows the benchmark component universe, prefer `index_ids` "
        "to avoid full-catalog scans."
    ),
)
async def fetch_index_catalog(
    request: IndexCatalogRequest,
    integration_service: IntegrationService = Depends(get_integration_service),
) -> IndexCatalogResponse:
    return cast(
        IndexCatalogResponse,
        await integration_service.list_index_catalog(
            as_of_date=request.as_of_date,
            index_ids=request.index_ids,
            index_currency=request.index_currency,
            index_type=request.index_type,
            index_status=request.index_status,
        ),
    )


@router.post(
    "/benchmarks/{benchmark_id}/market-series",
    response_model=BenchmarkMarketSeriesResponse,
    summary="Fetch benchmark market series inputs",
    description=(
        "What: Return benchmark market series inputs required by lotus-performance.\n"
        "How: Resolves components and returns aligned raw series honoring requested "
        "series_fields, deterministic paging, and benchmark-to-target FX context semantics.\n"
        "When: Used by lotus-performance and other downstream benchmark sourcing workflows that "
        "need native component series plus benchmark-to-target FX context. The response "
        "publishes native component series plus optional benchmark-to-target FX context; "
        "lotus-performance owns benchmark math and any benchmark-currency normalization of "
        "component series."
    ),
    openapi_extra=source_data_product_openapi_extra("MarketDataWindow"),
)
async def fetch_benchmark_market_series(
    request: BenchmarkMarketSeriesRequest,
    benchmark_id: str = Path(
        ...,
        description="Benchmark identifier for the requested market series input contract.",
        examples=["BENCH-SP500-TR"],
    ),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> BenchmarkMarketSeriesResponse:
    try:
        return cast(
            BenchmarkMarketSeriesResponse,
            await integration_service.get_benchmark_market_series(
                benchmark_id=benchmark_id, request=request
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/indices/{index_id}/price-series",
    response_model=IndexPriceSeriesResponse,
    summary="Fetch raw index price series",
    description=(
        "What: Return raw index price series for the requested index and window.\n"
        "How: Reads canonical time series records with deterministic ordering.\n"
        "When: Used directly by lotus-performance stateful benchmark sourcing and other "
        "downstream benchmark workflows that require raw index price inputs for calculation, "
        "validation, or evidence. This is source reference data, not a normalized "
        "benchmark-engine output contract."
    ),
    openapi_extra=source_data_product_openapi_extra("IndexSeriesWindow"),
)
async def fetch_index_price_series(
    request: IndexSeriesRequest,
    index_id: str = Path(
        ...,
        description="Index identifier for the requested raw price series.",
        examples=["IDX-SP500"],
    ),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> IndexPriceSeriesResponse:
    return cast(
        IndexPriceSeriesResponse,
        await integration_service.get_index_price_series(index_id=index_id, request=request),
    )


@router.post(
    "/indices/{index_id}/return-series",
    response_model=IndexReturnSeriesResponse,
    summary="Fetch raw index return series",
    description=(
        "What: Return raw vendor-provided index return series.\n"
        "How: Reads canonical index return records with explicit convention fields.\n"
        "When: Used by lotus-performance and other downstream workflows when raw provider return "
        "inputs are required for validation, evidence, or explicit return-series sourcing. This "
        "is a raw source contract, not a substitute for benchmark composition plus market-series "
        "inputs when lower-level benchmark reconstruction is required."
    ),
    openapi_extra=source_data_product_openapi_extra("IndexSeriesWindow"),
)
async def fetch_index_return_series(
    request: IndexSeriesRequest,
    index_id: str = Path(
        ...,
        description="Index identifier for the requested raw return series.",
        examples=["IDX-SP500"],
    ),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> IndexReturnSeriesResponse:
    return cast(
        IndexReturnSeriesResponse,
        await integration_service.get_index_return_series(index_id=index_id, request=request),
    )


@router.post(
    "/benchmarks/{benchmark_id}/return-series",
    response_model=BenchmarkReturnSeriesResponse,
    summary="Fetch raw benchmark return series",
    description=(
        "What: Return raw vendor-provided benchmark return series.\n"
        "How: Reads canonical benchmark return records with explicit convention fields.\n"
        "When: Used directly by lotus-performance vendor-series sourcing and other downstream "
        "workflows when provider benchmark return inputs are available for validation, evidence, "
        "or explicit override modes. This is not the default benchmark-math source when "
        "lower-level benchmark composition and market-series contracts are available."
    ),
)
async def fetch_benchmark_return_series(
    request: BenchmarkReturnSeriesRequest,
    benchmark_id: str = Path(
        ...,
        description="Benchmark identifier for the requested raw return series.",
        examples=["BENCH-SP500-TR"],
    ),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> BenchmarkReturnSeriesResponse:
    return cast(
        BenchmarkReturnSeriesResponse,
        await integration_service.get_benchmark_return_series(
            benchmark_id=benchmark_id,
            request=request,
        ),
    )


@router.post(
    "/reference/risk-free-series",
    response_model=RiskFreeSeriesResponse,
    summary="Fetch raw risk-free series",
    description=(
        "What: Return raw risk-free reference series for requested currency and window.\n"
        "How: Serves canonical risk-free records with convention metadata and lineage.\n"
        "When: Used by lotus-performance and lotus-risk for excess return, Sharpe, and "
        "risk-adjusted analytics inputs. Empty `points` means the route is reachable but "
        "usable source data is absent for the requested currency/window, so downstream "
        "readiness checks should treat that as a data-availability gap rather than a "
        "fallback-to-zero methodology signal."
    ),
    openapi_extra=source_data_product_openapi_extra("RiskFreeSeriesWindow"),
)
async def fetch_risk_free_series(
    request: RiskFreeSeriesRequest,
    integration_service: IntegrationService = Depends(get_integration_service),
) -> RiskFreeSeriesResponse:
    return cast(
        RiskFreeSeriesResponse,
        await integration_service.get_risk_free_series(request=request),
    )


@router.post(
    "/reference/classification-taxonomy",
    response_model=ClassificationTaxonomyResponse,
    summary="Fetch canonical classification taxonomy",
    description=(
        "What: Return effective classification taxonomy records.\n"
        "How: Applies as-of effective dating and optional scope filtering.\n"
        "When: Used by downstream consumers that need governed shared classification labels "
        "instead of local taxonomy drift. Missing labels remain absent rather than synthesized, "
        "so consumers can distinguish governed coverage gaps from valid source-owned "
        "classifications."
    ),
    openapi_extra=source_data_product_openapi_extra("InstrumentReferenceBundle"),
)
async def fetch_classification_taxonomy(
    request: ClassificationTaxonomyRequest,
    integration_service: IntegrationService = Depends(get_integration_service),
) -> ClassificationTaxonomyResponse:
    return cast(
        ClassificationTaxonomyResponse,
        await integration_service.get_classification_taxonomy(
            as_of_date=request.as_of_date,
            taxonomy_scope=request.taxonomy_scope,
        ),
    )


@router.post(
    "/benchmarks/{benchmark_id}/coverage",
    response_model=CoverageResponse,
    summary="Get benchmark reference coverage",
    description=(
        "What: Return benchmark reference data coverage diagnostics for an expected window.\n"
        "How: Compares expected window dates against observed data and summarizes "
        "quality distribution.\n"
        "When: Used by downstream readiness or support flows before benchmark-aware analytics "
        "processing. This route publishes source-data readiness evidence, not benchmark returns "
        "or benchmark-engine outputs."
    ),
    openapi_extra=source_data_product_openapi_extra("DataQualityCoverageReport"),
)
async def get_benchmark_coverage(
    request: CoverageRequest,
    benchmark_id: str = Path(
        ...,
        description="Benchmark identifier for the requested coverage diagnostics.",
        examples=["BENCH-SP500-TR"],
    ),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> CoverageResponse:
    return cast(
        CoverageResponse,
        await integration_service.get_benchmark_coverage(
            benchmark_id=benchmark_id,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        ),
    )


@router.post(
    "/reference/risk-free-series/coverage",
    response_model=CoverageResponse,
    summary="Get risk-free reference coverage",
    description=(
        "What: Return risk-free series coverage diagnostics for an expected window.\n"
        "How: Compares expected window dates against observed data and summarizes "
        "quality distribution.\n"
        "When: Used by lotus-risk and other readiness/support flows that need deterministic "
        "risk-free availability evidence before downstream analytics proceed. A response with "
        "`total_points = 0` and null observed bounds indicates an upstream data-availability gap "
        "for the requested currency/window."
    ),
    openapi_extra=source_data_product_openapi_extra("DataQualityCoverageReport"),
)
async def get_risk_free_coverage(
    currency: str = Query(..., description="Risk-free series currency.", examples=["USD"]),
    request: CoverageRequest = Body(...),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> CoverageResponse:
    return cast(
        CoverageResponse,
        await integration_service.get_risk_free_coverage(
            currency=currency,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        ),
    )
