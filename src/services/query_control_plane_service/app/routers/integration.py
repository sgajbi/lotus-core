from typing import cast

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, status
from portfolio_common.db import get_async_db_session
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
    BenchmarkDefinitionRequest,
    BenchmarkDefinitionResponse,
    BenchmarkMarketSeriesRequest,
    BenchmarkMarketSeriesResponse,
    BenchmarkReturnSeriesRequest,
    BenchmarkReturnSeriesResponse,
    ClassificationTaxonomyRequest,
    ClassificationTaxonomyResponse,
    CoverageRequest,
    CoverageResponse,
    IndexCatalogRequest,
    IndexCatalogResponse,
    IndexPriceSeriesResponse,
    IndexReturnSeriesResponse,
    IndexSeriesRequest,
    RiskFreeSeriesRequest,
    RiskFreeSeriesResponse,
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

router = APIRouter(prefix="/integration", tags=["Integration Contracts"])

INTEGRATION_POLICY_BLOCKED_EXAMPLE = {
    "detail": "SNAPSHOT_SECTIONS_BLOCKED_BY_POLICY: positions_projected"
}
CORE_SNAPSHOT_NOT_FOUND_EXAMPLE = {"detail": "Portfolio PORT-INT-001 not found"}
CORE_SNAPSHOT_CONFLICT_EXAMPLE = {
    "detail": "Simulation session SIM-20260310-0001 expected version mismatch"
}
CORE_SNAPSHOT_UNAVAILABLE_EXAMPLE = {
    "detail": "Section portfolio_totals requires valuation dependencies that are not available."
}
INSTRUMENT_ENRICHMENT_INVALID_EXAMPLE = {
    "detail": "security_ids must contain at least one identifier"
}


def get_integration_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> IntegrationService:
    return IntegrationService(db)


def get_core_snapshot_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> CoreSnapshotService:
    return CoreSnapshotService(db)


@router.get(
    "/policy/effective",
    response_model=EffectiveIntegrationPolicyResponse,
    summary="Get effective lotus-core integration policy",
    description=(
        "Returns effective policy diagnostics and provenance for the given consumer and tenant "
        "context, including strict-mode behavior and allowed sections."
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
        status.HTTP_400_BAD_REQUEST: {
            "description": "Invalid request payload or invalid section/mode combination."
        },
        status.HTTP_403_FORBIDDEN: {
            "description": "Requested sections are blocked by strict integration policy.",
            "content": {"application/json": {"example": INTEGRATION_POLICY_BLOCKED_EXAMPLE}},
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Portfolio or simulation session not found.",
            "content": {"application/json": {"example": CORE_SNAPSHOT_NOT_FOUND_EXAMPLE}},
        },
        status.HTTP_409_CONFLICT: {
            "description": "Simulation expected version mismatch or portfolio/session conflict.",
            "content": {"application/json": {"example": CORE_SNAPSHOT_CONFLICT_EXAMPLE}},
        },
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "description": "Section cannot be fulfilled due to missing valuation dependencies.",
            "content": {"application/json": {"example": CORE_SNAPSHOT_UNAVAILABLE_EXAMPLE}},
        },
    },
    summary="Generate a generic core snapshot",
    description=(
        "Returns baseline or simulation snapshot sections for an integration consumer. "
        "Supports positions baseline/projected/delta, portfolio totals, and instrument enrichment."
    ),
)
async def create_core_snapshot(
    request: CoreSnapshotRequest,
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier for the snapshot request.",
        examples=["PORT-INT-001"],
    ),
    consumer_system: str = Query(
        "lotus-performance",
        description="Downstream consumer system requesting the core snapshot.",
        examples=["lotus-performance"],
    ),
    tenant_id: str = Query(
        "default",
        description="Tenant identifier used for policy resolution.",
        examples=["tenant_sg_pb"],
    ),
    service: CoreSnapshotService = Depends(get_core_snapshot_service),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> CoreSnapshotResponse:
    requested_sections = list(request.sections)
    requested_policy_sections = [section.value.upper() for section in requested_sections]
    policy = integration_service.get_effective_policy(
        consumer_system=consumer_system,
        tenant_id=tenant_id,
        include_sections=requested_policy_sections,
    )
    allowed_policy_sections = set(policy.allowed_sections)
    if "NO_ALLOWED_SECTION_RESTRICTION" in policy.warnings:
        applied_sections = requested_sections
        dropped_sections: list[CoreSnapshotSection] = []
        warnings = list(policy.warnings)
    else:
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

    if dropped_sections and policy.policy_provenance.strict_mode:
        dropped = ", ".join(section.value for section in dropped_sections)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"SNAPSHOT_SECTIONS_BLOCKED_BY_POLICY: {dropped}",
        )

    if not applied_sections:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No sections remain after policy evaluation.",
        )

    effective_request = request.model_copy(update={"sections": applied_sections})
    governance = SnapshotGovernanceContext(
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

    try:
        response = await service.get_core_snapshot(
            portfolio_id=portfolio_id,
            request=effective_request,
            governance=governance,
        )
        return cast(CoreSnapshotResponse, response)
    except CoreSnapshotBadRequestError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except CoreSnapshotNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except CoreSnapshotConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except CoreSnapshotUnavailableSectionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.post(
    "/instruments/enrichment-bulk",
    response_model=InstrumentEnrichmentBulkResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "Invalid request payload.",
            "content": {"application/json": {"example": INSTRUMENT_ENRICHMENT_INVALID_EXAMPLE}},
        },
    },
    summary="Resolve issuer enrichment for security identifiers",
    description=(
        "Returns issuer enrichment for a caller-provided security_id list. "
        "Records are deterministic and preserve request order. Unknown securities are returned "
        "with null issuer fields."
    ),
)
async def get_instrument_enrichment_bulk(
    request: InstrumentEnrichmentBulkRequest,
    service: CoreSnapshotService = Depends(get_core_snapshot_service),
) -> InstrumentEnrichmentBulkResponse:
    try:
        records = await service.get_instrument_enrichment_bulk(request.security_ids)
        return InstrumentEnrichmentBulkResponse(records=records)
    except CoreSnapshotBadRequestError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/portfolios/{portfolio_id}/benchmark-assignment",
    response_model=BenchmarkAssignmentResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "No effective benchmark assignment found."},
    },
    summary="Resolve effective portfolio benchmark assignment",
    description=(
        "What: Resolve benchmark assignment for a portfolio as-of a point-in-time date.\n"
        "How: Applies effective-dating and assignment version ordering to return "
        "deterministic match.\n"
        "When: Used by lotus-performance before benchmark analytics workflows."
    ),
)
async def resolve_portfolio_benchmark_assignment(
    portfolio_id: str,
    request: BenchmarkAssignmentRequest,
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No effective benchmark assignment found for portfolio and as_of_date.",
        )
    return response


@router.post(
    "/benchmarks/{benchmark_id}/definition",
    response_model=BenchmarkDefinitionResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "No effective benchmark definition found."}
    },
    summary="Fetch effective benchmark definition",
    description=(
        "What: Return effective benchmark definition for an as-of date.\n"
        "How: Resolves benchmark master fields and composition records with effective dating.\n"
        "When: Used by lotus-performance to construct benchmark input context."
    ),
)
async def fetch_benchmark_definition(
    benchmark_id: str,
    request: BenchmarkDefinitionRequest,
    integration_service: IntegrationService = Depends(get_integration_service),
) -> BenchmarkDefinitionResponse:
    response = cast(
        BenchmarkDefinitionResponse | None,
        await integration_service.get_benchmark_definition(benchmark_id, request.as_of_date),
    )
    if response is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No effective benchmark definition found for benchmark_id and as_of_date.",
        )
    return response


@router.post(
    "/benchmarks/catalog",
    response_model=BenchmarkCatalogResponse,
    summary="Fetch benchmark master catalog",
    description=(
        "What: Return benchmark master records effective on a requested date.\n"
        "How: Applies optional filters and effective dating in query service.\n"
        "When: Used by downstream integration workflows to discover valid benchmark references."
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
        "How: Applies optional filters and effective dating in query service.\n"
        "When: Used by lotus-performance and attribution pipelines to discover "
        "canonical index metadata."
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
        "How: Resolves components and returns aligned raw series with quality and "
        "lineage metadata.\n"
        "When: Used for benchmark analytics and replay-safe portfolio attribution calculations."
    ),
)
async def fetch_benchmark_market_series(
    benchmark_id: str,
    request: BenchmarkMarketSeriesRequest,
    integration_service: IntegrationService = Depends(get_integration_service),
) -> BenchmarkMarketSeriesResponse:
    return cast(
        BenchmarkMarketSeriesResponse,
        await integration_service.get_benchmark_market_series(
            benchmark_id=benchmark_id, request=request
        ),
    )


@router.post(
    "/indices/{index_id}/price-series",
    response_model=IndexPriceSeriesResponse,
    summary="Fetch raw index price series",
    description=(
        "What: Return raw index price series for the requested index and window.\n"
        "How: Reads canonical time series records with deterministic ordering.\n"
        "When: Used by downstream analytics pipelines requiring raw index price inputs."
    ),
)
async def fetch_index_price_series(
    index_id: str,
    request: IndexSeriesRequest,
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
        "When: Used by lotus-performance for return-based benchmark processing."
    ),
)
async def fetch_index_return_series(
    index_id: str,
    request: IndexSeriesRequest,
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
        "When: Used by lotus-performance when provider benchmark return inputs are available."
    ),
)
async def fetch_benchmark_return_series(
    benchmark_id: str,
    request: BenchmarkReturnSeriesRequest,
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
        "When: Used by lotus-performance for excess return and risk-adjusted analytics inputs."
    ),
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
        "When: Used by lotus-performance attribution workflows to enforce shared domain labels."
    ),
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
        "When: Used by ops monitoring and pre-run validation before analytics processing."
    ),
)
async def get_benchmark_coverage(
    benchmark_id: str,
    request: CoverageRequest,
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
        "When: Used by ops monitoring and analytics readiness checks."
    ),
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
