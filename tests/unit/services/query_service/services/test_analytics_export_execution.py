from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.query_service.app.dtos.analytics_input_dto import (
    PortfolioAnalyticsTimeseriesRequest,
    PositionAnalyticsTimeseriesRequest,
)
from src.services.query_service.app.services.analytics_export_execution import (
    PORTFOLIO_EXPORT_PAGE_SIZE,
    POSITION_EXPORT_PAGE_SIZE,
    collect_portfolio_timeseries_for_export,
    collect_position_timeseries_for_export,
)


@pytest.mark.asyncio
async def test_collect_portfolio_timeseries_for_export_pages_until_token_exhausted() -> None:
    get_portfolio_timeseries = AsyncMock(
        side_effect=[
            SimpleNamespace(
                observations=[SimpleNamespace(model_dump=lambda mode="json": {"d": "1"})],
                page=SimpleNamespace(next_page_token="n1"),
            ),
            SimpleNamespace(
                observations=[SimpleNamespace(model_dump=lambda mode="json": {"d": "2"})],
                page=SimpleNamespace(next_page_token=None),
            ),
        ]
    )

    rows, depth = await collect_portfolio_timeseries_for_export(
        portfolio_id="P1",
        request=PortfolioAnalyticsTimeseriesRequest(as_of_date="2025-12-31", period="one_month"),
        get_portfolio_timeseries=get_portfolio_timeseries,
    )

    assert rows == [{"d": "1"}, {"d": "2"}]
    assert depth == 2
    first_request = get_portfolio_timeseries.await_args_list[0].kwargs["request"]
    second_request = get_portfolio_timeseries.await_args_list[1].kwargs["request"]
    assert first_request.page.page_size == PORTFOLIO_EXPORT_PAGE_SIZE
    assert first_request.page.page_token is None
    assert second_request.page.page_token == "n1"


@pytest.mark.asyncio
async def test_collect_position_timeseries_for_export_pages_until_token_exhausted() -> None:
    get_position_timeseries = AsyncMock(
        side_effect=[
            SimpleNamespace(
                rows=[SimpleNamespace(model_dump=lambda mode="json": {"p": "1"})],
                page=SimpleNamespace(next_page_token="n1"),
            ),
            SimpleNamespace(
                rows=[SimpleNamespace(model_dump=lambda mode="json": {"p": "2"})],
                page=SimpleNamespace(next_page_token=None),
            ),
        ]
    )

    rows, depth = await collect_position_timeseries_for_export(
        portfolio_id="P1",
        request=PositionAnalyticsTimeseriesRequest(as_of_date="2025-12-31", period="one_month"),
        get_position_timeseries=get_position_timeseries,
    )

    assert rows == [{"p": "1"}, {"p": "2"}]
    assert depth == 2
    first_request = get_position_timeseries.await_args_list[0].kwargs["request"]
    second_request = get_position_timeseries.await_args_list[1].kwargs["request"]
    assert first_request.page.page_size == POSITION_EXPORT_PAGE_SIZE
    assert first_request.page.page_token is None
    assert second_request.page.page_token == "n1"
