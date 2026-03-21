from __future__ import annotations

from typing import Literal, NoReturn, cast

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from fastapi.responses import Response
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

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

router = APIRouter(prefix="/integration", tags=["Integration Contracts"])

PORTFOLIO_ANALYTICS_NOT_FOUND_EXAMPLE = {"detail": "Portfolio not found."}
ANALYTICS_INVALID_REQUEST_EXAMPLE = {"detail": "Exactly one of window or period must be provided."}
ANALYTICS_INSUFFICIENT_DATA_EXAMPLE = {"detail": "Missing FX rate for EUR/USD on 2025-01-31."}
ANALYTICS_EXPORT_JOB_NOT_FOUND_EXAMPLE = {"detail": "Analytics export job JOB-AN-0001 not found."}
ANALYTICS_EXPORT_INCOMPLETE_EXAMPLE = {
    "detail": "Analytics export job JOB-AN-0001 is not complete."
}
HTTP_422_UNPROCESSABLE_CONTENT = 422


def get_analytics_timeseries_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> AnalyticsTimeseriesService:
    return AnalyticsTimeseriesService(db)


def _raise_http_for_analytics_error(exc: AnalyticsInputError) -> NoReturn:
    if exc.code == "RESOURCE_NOT_FOUND":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if exc.code == "INVALID_REQUEST":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if exc.code == "INSUFFICIENT_DATA":
        raise HTTPException(status_code=HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    if exc.code == "UNSUPPORTED_CONFIGURATION":
        raise HTTPException(status_code=HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post(
    "/portfolios/{portfolio_id}/analytics/portfolio-timeseries",
    response_model=PortfolioAnalyticsTimeseriesResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "Invalid request contract.",
            "content": {"application/json": {"example": ANALYTICS_INVALID_REQUEST_EXAMPLE}},
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Portfolio not found.",
            "content": {"application/json": {"example": PORTFOLIO_ANALYTICS_NOT_FOUND_EXAMPLE}},
        },
        HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Insufficient data or unsupported configuration.",
            "content": {"application/json": {"example": ANALYTICS_INSUFFICIENT_DATA_EXAMPLE}},
        },
    },
    summary="Fetch portfolio analytics timeseries inputs",
    description=(
        "What: Return canonical portfolio valuation and cash-flow timeseries required by "
        "lotus-performance.\n"
        "How: Resolve effective window, apply deterministic paging, and include "
        "lineage/quality diagnostics. Returned cash_flows are canonical portfolio-level "
        "events expressed in the effective reporting currency.\n"
        "When: Used for stateful TWR and MWR input acquisition without direct database coupling."
    ),
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
        status.HTTP_400_BAD_REQUEST: {
            "description": "Invalid request contract.",
            "content": {"application/json": {"example": ANALYTICS_INVALID_REQUEST_EXAMPLE}},
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Portfolio not found.",
            "content": {"application/json": {"example": PORTFOLIO_ANALYTICS_NOT_FOUND_EXAMPLE}},
        },
        HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Insufficient data or unsupported configuration.",
            "content": {"application/json": {"example": ANALYTICS_INSUFFICIENT_DATA_EXAMPLE}},
        },
    },
    summary="Fetch position analytics timeseries inputs",
    description=(
        "What: Return canonical position-level valuation timeseries required by "
        "contribution and attribution analytics.\n"
        "How: Apply deterministic paging and optional dimension/filter selectors while "
        "keeping enrichment separate. Cash-flow rows are included by default because "
        "acquisition-day analytics are unsafe without them.\n"
        "When: Used by lotus-performance analytics pipelines for large-window "
        "position input retrieval."
    ),
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
        status.HTTP_404_NOT_FOUND: {
            "description": "Portfolio not found.",
            "content": {"application/json": {"example": PORTFOLIO_ANALYTICS_NOT_FOUND_EXAMPLE}},
        },
    },
    summary="Fetch analytics portfolio reference metadata",
    description=(
        "What: Return portfolio-level reference metadata for analytics joins and "
        "lifecycle context.\n"
        "How: Resolve canonical portfolio attributes with lineage metadata.\n"
        "When: Used alongside analytics timeseries endpoints to avoid repetitive "
        "metadata payload duplication."
    ),
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
        status.HTTP_400_BAD_REQUEST: {
            "description": "Invalid export request contract.",
            "content": {"application/json": {"example": ANALYTICS_INVALID_REQUEST_EXAMPLE}},
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Portfolio not found.",
            "content": {"application/json": {"example": PORTFOLIO_ANALYTICS_NOT_FOUND_EXAMPLE}},
        },
        HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Insufficient source data or unsupported configuration.",
            "content": {"application/json": {"example": ANALYTICS_INSUFFICIENT_DATA_EXAMPLE}},
        },
    },
    summary="Create analytics timeseries export job",
    description=(
        "What: Create a durable export job for portfolio or position analytics "
        "timeseries datasets.\n"
        "How: Validates canonical request payload, computes deterministic fingerprint, "
        "and persists lifecycle state.\n"
        "When: Used for large horizon extractions that should be retrieved "
        "asynchronously by downstream analytics."
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
        status.HTTP_404_NOT_FOUND: {
            "description": "Export job not found.",
            "content": {"application/json": {"example": ANALYTICS_EXPORT_JOB_NOT_FOUND_EXAMPLE}},
        },
    },
    summary="Fetch analytics export job status",
    description=(
        "What: Fetch lifecycle status for an analytics export job.\n"
        "How: Reads persisted job metadata and terminal status from canonical "
        "query-service storage.\n"
        "When: Used by polling clients before attempting result retrieval."
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
        status.HTTP_404_NOT_FOUND: {
            "description": "Export job not found.",
            "content": {"application/json": {"example": ANALYTICS_EXPORT_JOB_NOT_FOUND_EXAMPLE}},
        },
        HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Export job is incomplete or source payload unavailable.",
            "content": {"application/json": {"example": ANALYTICS_EXPORT_INCOMPLETE_EXAMPLE}},
        },
    },
    summary="Fetch analytics export job result",
    description=(
        "What: Retrieve finalized export payload for a completed analytics export job.\n"
        "How: Returns JSON envelope or NDJSON stream with optional gzip encoding.\n"
        "When: Used by lotus-performance batch pipelines after job completion."
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
