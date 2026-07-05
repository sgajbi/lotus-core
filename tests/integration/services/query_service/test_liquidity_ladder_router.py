from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio

from src.services.query_service.app.dependencies import get_liquidity_ladder_service
from src.services.query_service.app.dtos.source_data_product_identity import (
    source_data_product_runtime_metadata,
)
from src.services.query_service.app.main import app
from src.services.query_service.app.services.liquidity_ladder_service import (
    PortfolioLiquidityLadderService,
)

pytestmark = pytest.mark.asyncio
BOUNDARY_NOTE = (
    "Source liquidity evidence only; not an advice, OMS execution, funding recommendation, "
    "best-execution, tax, or market-impact forecast."
)


def _runtime_metadata(as_of_date: date) -> dict:
    return {
        "product_name": "PortfolioLiquidityLadder",
        "product_version": "v1",
        **source_data_product_runtime_metadata(
            as_of_date=as_of_date,
            generated_at=datetime(2026, 3, 27, 12, 0, tzinfo=UTC),
            data_quality_status="COMPLETE",
        ),
    }


@pytest_asyncio.fixture
async def async_test_client():
    mock_service = AsyncMock(spec=PortfolioLiquidityLadderService)
    app.dependency_overrides[get_liquidity_ladder_service] = lambda: mock_service
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, mock_service
    app.dependency_overrides.pop(get_liquidity_ladder_service, None)


async def test_get_liquidity_ladder(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_liquidity_ladder.return_value = {
        "portfolio_id": "P1",
        "portfolio_currency": "USD",
        "resolved_as_of_date": date(2026, 3, 27),
        "horizon_days": 30,
        "include_projected": True,
        "totals": {
            "opening_cash_balance_portfolio_currency": Decimal("250000"),
            "projected_cash_available_end_portfolio_currency": Decimal("240000"),
            "maximum_cash_shortfall_portfolio_currency": Decimal("0"),
            "non_cash_market_value_portfolio_currency": Decimal("750000"),
            "non_cash_position_count": 3,
        },
        "buckets": [],
        "asset_liquidity_tiers": [],
        "notes": BOUNDARY_NOTE,
        **_runtime_metadata(date(2026, 3, 27)),
    }

    response = await client.get(
        "/portfolios/P1/liquidity-ladder",
        params={"as_of_date": "2026-03-27", "horizon_days": "30", "include_projected": "true"},
    )

    assert response.status_code == 200
    assert response.json()["product_name"] == "PortfolioLiquidityLadder"
    mock_service.get_liquidity_ladder.assert_awaited_once_with(
        portfolio_id="P1",
        as_of_date=date(2026, 3, 27),
        horizon_days=30,
        include_projected=True,
    )


async def test_get_liquidity_ladder_defaults_optional_query_params(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_liquidity_ladder.return_value = {
        "portfolio_id": "P1",
        "portfolio_currency": "USD",
        "resolved_as_of_date": date(2026, 3, 27),
        "horizon_days": 30,
        "include_projected": True,
        "totals": {
            "opening_cash_balance_portfolio_currency": Decimal("0"),
            "projected_cash_available_end_portfolio_currency": Decimal("0"),
            "maximum_cash_shortfall_portfolio_currency": Decimal("0"),
            "non_cash_market_value_portfolio_currency": Decimal("0"),
            "non_cash_position_count": 0,
        },
        "buckets": [],
        "asset_liquidity_tiers": [],
        "notes": BOUNDARY_NOTE,
        **_runtime_metadata(date(2026, 3, 27)),
    }

    response = await client.get("/portfolios/P1/liquidity-ladder")

    assert response.status_code == 200
    mock_service.get_liquidity_ladder.assert_awaited_once_with(
        portfolio_id="P1",
        as_of_date=None,
        horizon_days=30,
        include_projected=True,
    )


async def test_get_liquidity_ladder_maps_missing_portfolio_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_liquidity_ladder.side_effect = ValueError("Portfolio with id P404 not found")

    response = await client.get("/portfolios/P404/liquidity-ladder")

    assert response.status_code == 404
    assert response.json()["detail"] == "Portfolio with id P404 not found"


async def test_get_liquidity_ladder_maps_generic_not_found_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_liquidity_ladder.side_effect = ValueError("not found")

    response = await client.get("/portfolios/P404/liquidity-ladder")

    assert response.status_code == 404
    assert response.json()["detail"] == "not found"


async def test_get_liquidity_ladder_maps_resolution_errors_to_400(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_liquidity_ladder.side_effect = ValueError(
        "No business date is available for liquidity ladder queries."
    )

    response = await client.get("/portfolios/P1/liquidity-ladder")

    assert response.status_code == 400
    assert (
        response.json()["detail"] == "No business date is available for liquidity ladder queries."
    )


async def test_get_liquidity_ladder_unexpected_uses_global_500_envelope(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_liquidity_ladder.side_effect = RuntimeError("boom")

    response = await client.get("/portfolios/P1/liquidity-ladder")

    assert response.status_code == 500
    assert response.json()["error"] == "Internal Server Error"
    assert "correlation_id" in response.json()
