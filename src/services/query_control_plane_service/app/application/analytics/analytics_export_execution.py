"""Bounded page collection workflows for analytics export datasets."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import NamedTuple

from ...contracts.analytics_export_evidence import (
    AnalyticsExportPageEvidence,
    AnalyticsExportSourceEvidence,
)
from ...contracts.analytics_inputs import (
    PortfolioAnalyticsTimeseriesRequest,
    PortfolioAnalyticsTimeseriesResponse,
    PositionAnalyticsTimeseriesRequest,
    PositionAnalyticsTimeseriesResponse,
)
from .analytics_export_evidence import (
    export_page_evidence,
    export_source_evidence,
    retain_export_page,
)

PORTFOLIO_EXPORT_PAGE_SIZE = 2000
POSITION_EXPORT_PAGE_SIZE = 2000


class AnalyticsExportDataset(NamedTuple):
    data_rows: list[dict[str, object]]
    page_depth: int
    source_evidence: AnalyticsExportSourceEvidence


async def collect_portfolio_timeseries_for_export(
    *,
    portfolio_id: str,
    request: PortfolioAnalyticsTimeseriesRequest,
    get_portfolio_timeseries: Callable[..., Awaitable[PortfolioAnalyticsTimeseriesResponse]],
) -> AnalyticsExportDataset:
    rows: list[dict[str, object]] = []
    evidence: list[AnalyticsExportPageEvidence] = []
    known_cuts: set[str] = set()
    page_depth = 0
    page_token: str | None = None
    while True:
        page_depth += 1
        page_request = request.page.model_copy(
            update={"page_token": page_token, "page_size": PORTFOLIO_EXPORT_PAGE_SIZE}
        )
        paged_request = request.model_copy(update={"page": page_request})
        response = await get_portfolio_timeseries(
            portfolio_id=portfolio_id,
            request=paged_request,
        )
        rows.extend([item.model_dump(mode="json") for item in response.observations])
        retain_export_page(
            evidence,
            export_page_evidence(
                response=response,
                request=request,
                page_number=page_depth,
                row_count=len(response.observations),
            ),
            known_cuts,
        )
        page_token = response.page.next_page_token
        if not page_token:
            break
    return AnalyticsExportDataset(rows, page_depth, export_source_evidence(evidence))


async def collect_position_timeseries_for_export(
    *,
    portfolio_id: str,
    request: PositionAnalyticsTimeseriesRequest,
    get_position_timeseries: Callable[..., Awaitable[PositionAnalyticsTimeseriesResponse]],
) -> AnalyticsExportDataset:
    rows: list[dict[str, object]] = []
    evidence: list[AnalyticsExportPageEvidence] = []
    known_cuts: set[str] = set()
    page_depth = 0
    page_token: str | None = None
    while True:
        page_depth += 1
        page_request = request.page.model_copy(
            update={"page_token": page_token, "page_size": POSITION_EXPORT_PAGE_SIZE}
        )
        paged_request = request.model_copy(update={"page": page_request})
        response = await get_position_timeseries(
            portfolio_id=portfolio_id,
            request=paged_request,
        )
        rows.extend([item.model_dump(mode="json") for item in response.rows])
        retain_export_page(
            evidence,
            export_page_evidence(
                response=response,
                request=request,
                page_number=page_depth,
                row_count=len(response.rows),
            ),
            known_cuts,
        )
        page_token = response.page.next_page_token
        if not page_token:
            break
    return AnalyticsExportDataset(rows, page_depth, export_source_evidence(evidence))
