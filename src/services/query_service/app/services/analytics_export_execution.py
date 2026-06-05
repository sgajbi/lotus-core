from __future__ import annotations

from collections.abc import Awaitable, Callable

from ..dtos.analytics_input_dto import (
    PortfolioAnalyticsTimeseriesRequest,
    PositionAnalyticsTimeseriesRequest,
)

PORTFOLIO_EXPORT_PAGE_SIZE = 2000
POSITION_EXPORT_PAGE_SIZE = 2000


async def collect_portfolio_timeseries_for_export(
    *,
    portfolio_id: str,
    request: PortfolioAnalyticsTimeseriesRequest,
    get_portfolio_timeseries: Callable[..., Awaitable[object]],
) -> tuple[list[dict[str, object]], int]:
    rows: list[dict[str, object]] = []
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
        page_token = response.page.next_page_token
        if not page_token:
            break
    return rows, page_depth


async def collect_position_timeseries_for_export(
    *,
    portfolio_id: str,
    request: PositionAnalyticsTimeseriesRequest,
    get_position_timeseries: Callable[..., Awaitable[object]],
) -> tuple[list[dict[str, object]], int]:
    rows: list[dict[str, object]] = []
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
        page_token = response.page.next_page_token
        if not page_token:
            break
    return rows, page_depth
