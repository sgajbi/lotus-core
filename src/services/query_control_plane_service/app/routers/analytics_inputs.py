from __future__ import annotations

from typing import Literal, NoReturn, cast

from fastapi import APIRouter, Depends, Path, Query, status
from fastapi.responses import Response
from portfolio_common.source_data_products import source_data_product_openapi_extra

from src.services.query_service.app.dtos.analytics_input_dto import (
    AnalyticsExportCreateRequest,
    AnalyticsExportJobResponse,
    AnalyticsExportJsonResultResponse,
    PortfolioAnalyticsReferenceRequest,
    PortfolioAnalyticsReferenceResponse,
    PortfolioAnalyticsTimeseriesRequest,
    PortfolioAnalyticsTimeseriesResponse,
    PositionAnalyticsTimeseriesRequest,
    PositionAnalyticsTimeseriesResponse,
)
from src.services.query_service.app.services.analytics_timeseries_service import (
    AnalyticsInputError,
    AnalyticsTimeseriesService,
)

from ..dependencies import get_analytics_timeseries_service
from .response_helpers import (
    problem_example,
    problem_or_validation_response,
    problem_response,
    raise_problem,
)

router = APIRouter(prefix="/integration", tags=["Integration Contracts"])

PORTFOLIO_ANALYTICS_NOT_FOUND_EXAMPLE = problem_example(
    status_code=status.HTTP_404_NOT_FOUND,
    title="Analytics source not found",
    detail="Requested analytics source was not found.",
    error_code="QCP_ANALYTICS_NOT_FOUND",
    metadata={"source_product": "PortfolioTimeseriesInput"},
)
ANALYTICS_INVALID_REQUEST_EXAMPLE = problem_example(
    status_code=status.HTTP_400_BAD_REQUEST,
    title="Analytics request is invalid",
    detail="Analytics request is invalid.",
    error_code="QCP_ANALYTICS_INVALID_REQUEST",
    metadata={"source_product": "PortfolioTimeseriesInput"},
)
ANALYTICS_INSUFFICIENT_DATA_EXAMPLE = problem_example(
    status_code=422,
    title="Analytics source data unavailable",
    detail="Required analytics source data is unavailable.",
    error_code="QCP_ANALYTICS_INSUFFICIENT_DATA",
    metadata={"source_product": "PortfolioTimeseriesInput"},
)
ANALYTICS_EXPORT_JOB_NOT_FOUND_EXAMPLE = problem_example(
    status_code=status.HTTP_404_NOT_FOUND,
    title="Analytics source not found",
    detail="Requested analytics source was not found.",
    error_code="QCP_ANALYTICS_NOT_FOUND",
    metadata={"source_product": "AnalyticsExportJob"},
)
ANALYTICS_EXPORT_INCOMPLETE_EXAMPLE = problem_example(
    status_code=422,
    title="Analytics source data unavailable",
    detail="Required analytics source data is unavailable.",
    error_code="QCP_ANALYTICS_INSUFFICIENT_DATA",
    metadata={"source_product": "AnalyticsExportJob"},
)
HTTP_422_UNPROCESSABLE_CONTENT = 422
ANALYTICS_ERROR_STATUS_MAP = {
    "RESOURCE_NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "INVALID_REQUEST": status.HTTP_400_BAD_REQUEST,
    "INSUFFICIENT_DATA": HTTP_422_UNPROCESSABLE_CONTENT,
    "UNSUPPORTED_CONFIGURATION": HTTP_422_UNPROCESSABLE_CONTENT,
}
ANALYTICS_ERROR_CONTRACTS = {
    "RESOURCE_NOT_FOUND": (
        "Analytics source not found",
        "Requested analytics source was not found.",
        "QCP_ANALYTICS_NOT_FOUND",
    ),
    "INVALID_REQUEST": (
        "Analytics request is invalid",
        "Analytics request is invalid.",
        "QCP_ANALYTICS_INVALID_REQUEST",
    ),
    "INSUFFICIENT_DATA": (
        "Analytics source data unavailable",
        "Required analytics source data is unavailable.",
        "QCP_ANALYTICS_INSUFFICIENT_DATA",
    ),
    "UNSUPPORTED_CONFIGURATION": (
        "Analytics configuration unsupported",
        "Requested analytics configuration is unsupported.",
        "QCP_ANALYTICS_UNSUPPORTED_CONFIGURATION",
    ),
}


def _raise_http_for_analytics_error(exc: AnalyticsInputError) -> NoReturn:
    status_code = ANALYTICS_ERROR_STATUS_MAP.get(
        exc.code,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
    title, detail, error_code = ANALYTICS_ERROR_CONTRACTS.get(
        exc.code,
        (
            "Analytics request failed",
            "Analytics request failed.",
            "QCP_ANALYTICS_ERROR",
        ),
    )
    raise_problem(
        status_code=status_code,
        title=title,
        detail=detail,
        error_code=error_code,
        metadata={"analytics_error_code": exc.code},
    )


@router.post(
    "/portfolios/{portfolio_id}/analytics/portfolio-timeseries",
    response_model=PortfolioAnalyticsTimeseriesResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: problem_response(
            "Invalid request contract.",
            ANALYTICS_INVALID_REQUEST_EXAMPLE,
        ),
        status.HTTP_404_NOT_FOUND: problem_response(
            "Portfolio not found.",
            PORTFOLIO_ANALYTICS_NOT_FOUND_EXAMPLE,
        ),
        HTTP_422_UNPROCESSABLE_CONTENT: problem_or_validation_response(
            "Insufficient data or unsupported configuration.",
            ANALYTICS_INSUFFICIENT_DATA_EXAMPLE,
        ),
    },
    summary="Fetch portfolio analytics timeseries inputs",
    description=(
        "What: Return canonical portfolio valuation and cash-flow timeseries required by "
        "lotus-performance and other governed downstream analytics consumers.\n"
        "How: Resolve effective window, apply deterministic paging, and include "
        "lineage/quality diagnostics. Returned cash_flows are canonical portfolio-level "
        "events expressed in the effective reporting currency with explicit flow provenance.\n"
        "When: Used directly for stateful TWR/MWR input acquisition in lotus-performance and "
        "kept available as a governed portfolio-level analytics-input contract for future "
        "downstream analytics sourcing without direct database coupling."
    ),
    openapi_extra=source_data_product_openapi_extra("PortfolioTimeseriesInput"),
)
async def get_portfolio_analytics_timeseries(
    request: PortfolioAnalyticsTimeseriesRequest,
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier for the requested analytics input contract.",
        examples=["PORT-AN-001"],
    ),
    service: AnalyticsTimeseriesService = Depends(get_analytics_timeseries_service),
) -> PortfolioAnalyticsTimeseriesResponse:
    try:
        return cast(
            PortfolioAnalyticsTimeseriesResponse,
            await service.get_portfolio_timeseries(portfolio_id=portfolio_id, request=request),
        )
    except AnalyticsInputError as exc:
        _raise_http_for_analytics_error(exc)


@router.post(
    "/portfolios/{portfolio_id}/analytics/position-timeseries",
    response_model=PositionAnalyticsTimeseriesResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: problem_response(
            "Invalid request contract.",
            ANALYTICS_INVALID_REQUEST_EXAMPLE,
        ),
        status.HTTP_404_NOT_FOUND: problem_response(
            "Portfolio not found.",
            PORTFOLIO_ANALYTICS_NOT_FOUND_EXAMPLE,
        ),
        HTTP_422_UNPROCESSABLE_CONTENT: problem_or_validation_response(
            "Insufficient data or unsupported configuration.",
            ANALYTICS_INSUFFICIENT_DATA_EXAMPLE,
        ),
    },
    summary="Fetch position analytics timeseries inputs",
    description=(
        "What: Return canonical position-level valuation timeseries required by "
        "performance contribution, performance attribution, and historical risk attribution.\n"
        "How: Apply deterministic paging and optional dimension/filter selectors while "
        "keeping enrichment separate. Cash-flow rows are included by default because "
        "acquisition-day analytics are unsafe without them, and they carry explicit "
        "internal versus external provenance.\n"
        "When: Used by lotus-performance and lotus-risk analytics pipelines for large-window "
        "position input retrieval without direct database coupling."
    ),
    openapi_extra=source_data_product_openapi_extra("PositionTimeseriesInput"),
)
async def get_position_analytics_timeseries(
    request: PositionAnalyticsTimeseriesRequest,
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier for the requested position analytics contract.",
        examples=["PORT-AN-001"],
    ),
    service: AnalyticsTimeseriesService = Depends(get_analytics_timeseries_service),
) -> PositionAnalyticsTimeseriesResponse:
    try:
        return cast(
            PositionAnalyticsTimeseriesResponse,
            await service.get_position_timeseries(portfolio_id=portfolio_id, request=request),
        )
    except AnalyticsInputError as exc:
        _raise_http_for_analytics_error(exc)


@router.post(
    "/portfolios/{portfolio_id}/analytics/reference",
    response_model=PortfolioAnalyticsReferenceResponse,
    responses={
        status.HTTP_404_NOT_FOUND: problem_response(
            "Portfolio not found.",
            PORTFOLIO_ANALYTICS_NOT_FOUND_EXAMPLE,
        ),
    },
    summary="Fetch analytics portfolio reference metadata",
    description=(
        "What: Return portfolio-level reference metadata for analytics joins and "
        "lifecycle context.\n"
        "How: Resolve current canonical portfolio reference fields, publish the latest complete "
        "performance_end_date where required portfolio and position analytics source families "
        "overlap, bound that date by the requested as_of_date, and include lineage metadata.\n"
        "When: Used by lotus-performance analytics pipelines and lotus-gateway workspace source "
        "context flows alongside analytics timeseries endpoints to avoid repetitive metadata "
        "payload duplication.\n"
        "Contract note: portfolio reference fields are current canonical portfolio state, "
        "not historical effective-dated portfolio snapshots."
    ),
    openapi_extra=source_data_product_openapi_extra("PortfolioAnalyticsReference"),
)
async def get_portfolio_analytics_reference(
    request: PortfolioAnalyticsReferenceRequest,
    portfolio_id: str = Path(
        ...,
        description="Portfolio identifier for the requested analytics reference contract.",
        examples=["PORT-AN-001"],
    ),
    service: AnalyticsTimeseriesService = Depends(get_analytics_timeseries_service),
) -> PortfolioAnalyticsReferenceResponse:
    try:
        return cast(
            PortfolioAnalyticsReferenceResponse,
            await service.get_portfolio_reference(portfolio_id=portfolio_id, request=request),
        )
    except AnalyticsInputError as exc:
        _raise_http_for_analytics_error(exc)


@router.post(
    "/exports/analytics-timeseries/jobs",
    response_model=AnalyticsExportJobResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: problem_response(
            "Invalid export request contract.",
            ANALYTICS_INVALID_REQUEST_EXAMPLE,
        ),
        status.HTTP_404_NOT_FOUND: problem_response(
            "Portfolio not found.",
            PORTFOLIO_ANALYTICS_NOT_FOUND_EXAMPLE,
        ),
        HTTP_422_UNPROCESSABLE_CONTENT: problem_or_validation_response(
            "Insufficient source data or unsupported configuration.",
            ANALYTICS_INSUFFICIENT_DATA_EXAMPLE,
        ),
    },
    summary="Create analytics timeseries export job",
    description=(
        "What: Create a durable export job for portfolio or position analytics "
        "timeseries datasets.\n"
        "How: Validates canonical request payload, computes deterministic fingerprint, "
        "persists lifecycle state, and reports explicit execution-mode and "
        "result-availability metadata.\n"
        "When: Used for large horizon extractions that should be retrieved "
        "through the export job contract rather than direct paged polling.\n"
        "Contract note: current lifecycle_mode is inline_job_execution, so jobs may "
        "complete within the create request."
    ),
)
async def create_analytics_export_job(
    request: AnalyticsExportCreateRequest,
    service: AnalyticsTimeseriesService = Depends(get_analytics_timeseries_service),
) -> AnalyticsExportJobResponse:
    try:
        return cast(AnalyticsExportJobResponse, await service.create_export_job(request))
    except AnalyticsInputError as exc:
        _raise_http_for_analytics_error(exc)


@router.get(
    "/exports/analytics-timeseries/jobs/{job_id}",
    response_model=AnalyticsExportJobResponse,
    responses={
        status.HTTP_404_NOT_FOUND: problem_response(
            "Export job not found.",
            ANALYTICS_EXPORT_JOB_NOT_FOUND_EXAMPLE,
        ),
    },
    summary="Fetch analytics export job status",
    description=(
        "What: Fetch lifecycle status for an analytics export job.\n"
        "How: Reads persisted job metadata and terminal status from canonical "
        "query-service storage, including result availability and deterministic "
        "result retrieval path.\n"
        "When: Used by polling clients before attempting result retrieval, especially for "
        "large-window extraction flows where direct page-by-page replay would be slower or "
        "operationally noisier than a durable export hand-off."
    ),
)
async def get_analytics_export_job(
    job_id: str = Path(
        ...,
        description="Durable analytics export job identifier.",
        examples=["JOB-AN-0001"],
    ),
    service: AnalyticsTimeseriesService = Depends(get_analytics_timeseries_service),
) -> AnalyticsExportJobResponse:
    try:
        return cast(AnalyticsExportJobResponse, await service.get_export_job(job_id))
    except AnalyticsInputError as exc:
        _raise_http_for_analytics_error(exc)


@router.get(
    "/exports/analytics-timeseries/jobs/{job_id}/result",
    response_model=AnalyticsExportJsonResultResponse,
    responses={
        status.HTTP_404_NOT_FOUND: problem_response(
            "Export job not found.",
            ANALYTICS_EXPORT_JOB_NOT_FOUND_EXAMPLE,
        ),
        HTTP_422_UNPROCESSABLE_CONTENT: problem_or_validation_response(
            (
                "Export job is incomplete, source payload unavailable, or requested "
                "serialization is unsupported."
            ),
            ANALYTICS_EXPORT_INCOMPLETE_EXAMPLE,
        ),
    },
    summary="Fetch analytics export job result",
    description=(
        "What: Retrieve finalized export payload for a completed analytics export job.\n"
        "How: Returns JSON envelope or NDJSON stream with optional gzip encoding and "
        "includes deterministic request/result provenance metadata.\n"
        "When: Used by lotus-performance batch pipelines and similar downstream bulk retrieval "
        "flows after job completion instead of repeatedly replaying large paged windows."
    ),
)
async def get_analytics_export_job_result(
    job_id: str = Path(
        ...,
        description="Durable analytics export job identifier.",
        examples=["JOB-AN-0001"],
    ),
    result_format: Literal["json", "ndjson"] = Query(
        "json",
        description="Preferred serialization format for export result retrieval.",
        examples=["json"],
    ),
    compression: Literal["none", "gzip"] = Query(
        "none",
        description="Optional transport compression for result retrieval.",
        examples=["gzip"],
    ),
    service: AnalyticsTimeseriesService = Depends(get_analytics_timeseries_service),
) -> AnalyticsExportJsonResultResponse | Response:
    try:
        if result_format == "ndjson":
            payload, media_type, content_encoding = await service.get_export_result_ndjson(
                job_id,
                compression=compression,
            )
            headers = {"Content-Encoding": content_encoding} if content_encoding == "gzip" else None
            return Response(content=payload, media_type=media_type, headers=headers)
        return cast(AnalyticsExportJsonResultResponse, await service.get_export_result_json(job_id))
    except AnalyticsInputError as exc:
        _raise_http_for_analytics_error(exc)
