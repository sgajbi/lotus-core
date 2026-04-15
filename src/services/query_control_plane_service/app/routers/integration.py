from typing import cast

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
BENCHMARK_ASSIGNMENT_NOT_FOUND_EXAMPLE = {
    "detail": "No effective benchmark assignment found for portfolio and as_of_date."
}
BENCHMARK_DEFINITION_NOT_FOUND_EXAMPLE = {
    "detail": "No effective benchmark definition found for benchmark_id and as_of_date."
}
BENCHMARK_COMPOSITION_WINDOW_NOT_FOUND_EXAMPLE = {
    "detail": "No overlapping benchmark definition found for benchmark_id and requested window."
}
HTTP_422_UNPROCESSABLE_CONTENT = 422


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
        HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Section cannot be fulfilled due to missing valuation dependencies.",
            "content": {"application/json": {"example": CORE_SNAPSHOT_UNAVAILABLE_EXAMPLE}},
        },
    },
    summary="Fetch governed core snapshot contract",
    description=(
        "What: Return a governed multi-section portfolio snapshot contract for downstream "
        "integration consumers.\n"
        "How: Applies tenant and consumer policy, resolves baseline or simulation state, "
        "and returns reproducibility metadata including request fingerprint and freshness.\n"
        "When: Used by downstream systems that need policy-aware positions, totals, "
        "delta, or enrichment views without direct query-service coupling."
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
    requested_sections = list(request.sections)
    requested_policy_sections = [section.value.upper() for section in requested_sections]
    policy = integration_service.get_effective_policy(
        consumer_system=request.consumer_system,
        tenant_id=request.tenant_id,
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
        raise HTTPException(status_code=HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/portfolios/{portfolio_id}/benchmark-assignment",
    response_model=BenchmarkAssignmentResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "No effective benchmark assignment found.",
            "content": {"application/json": {"example": BENCHMARK_ASSIGNMENT_NOT_FOUND_EXAMPLE}},
        },
    },
    summary="Resolve effective portfolio benchmark assignment",
    description=(
        "What: Resolve benchmark assignment for a portfolio as-of a point-in-time date.\n"
        "How: Applies effective-dating and assignment version ordering to return "
        "deterministic match. Resolution is keyed by portfolio_id and as_of_date; "
        "request reporting_currency and policy_context are caller-context fields and do "
        "not change assignment selection in the current implementation.\n"
        "When: Used by lotus-performance, lotus-risk, and reporting workflows before "
        "benchmark-aware analytics or evidence generation."
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No effective benchmark assignment found for portfolio and as_of_date.",
        )
    return response


@router.post(
    "/benchmarks/{benchmark_id}/composition-window",
    response_model=BenchmarkCompositionWindowResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "No overlapping benchmark definition found.",
            "content": {
                "application/json": {"example": BENCHMARK_COMPOSITION_WINDOW_NOT_FOUND_EXAMPLE}
            },
        },
        status.HTTP_409_CONFLICT: {
            "description": "Benchmark definition changed incompatibly inside the requested window."
        },
    },
    summary="Fetch overlapping benchmark composition segments",
    description=(
        "What: Return all effective benchmark composition segments overlapping a "
        "requested window.\n"
        "How: Resolves overlapping benchmark definition and composition records with deterministic "
        "ordering and without daily-expanding weights.\n"
        "When: Used by lotus-performance and other downstream consumers to calculate benchmark "
        "returns across rebalance windows. This is the strategic cross-rebalance source contract; "
        "single-date benchmark definition reads are not a substitute for long-window benchmark math."
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
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if response is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "No overlapping benchmark definition found for benchmark_id and requested window."
            ),
        )
    return response


@router.post(
    "/benchmarks/{benchmark_id}/definition",
    response_model=BenchmarkDefinitionResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "No effective benchmark definition found.",
            "content": {"application/json": {"example": BENCHMARK_DEFINITION_NOT_FOUND_EXAMPLE}},
        }
    },
    summary="Fetch effective benchmark definition",
    description=(
        "What: Return effective benchmark definition for an as-of date.\n"
        "How: Resolves benchmark master fields and composition records with effective dating.\n"
        "When: Used by lotus-performance to construct benchmark input context."
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
        "How: Resolves components and returns aligned raw series honoring requested "
        "series_fields, deterministic paging, and benchmark-to-target FX context semantics.\n"
        "When: Used by lotus-performance and lotus-risk for benchmark analytics and replay-safe "
        "portfolio or risk attribution calculations. The response publishes native component "
        "series plus optional benchmark-to-target FX context; lotus-performance owns benchmark "
        "math and any benchmark-currency normalization of component series."
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
        "When: Used by downstream analytics pipelines requiring raw index price inputs."
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
        "When: Used by lotus-performance for return-based benchmark processing."
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
        "When: Used by lotus-performance when provider benchmark return inputs are available."
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
        "When: Used by lotus-performance, lotus-risk, lotus-gateway, and lotus-advise to enforce "
        "shared classification labels instead of local taxonomy drift. Missing labels remain "
        "absent rather than synthesized, so downstream consumers can distinguish governed "
        "coverage gaps from valid source-owned classifications."
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
        "When: Used by ops monitoring and pre-run validation before analytics processing."
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
        "When: Used by ops monitoring and analytics readiness checks. A response with "
        "`total_points = 0` and null observed bounds indicates an upstream data-availability "
        "gap for the requested currency/window."
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
