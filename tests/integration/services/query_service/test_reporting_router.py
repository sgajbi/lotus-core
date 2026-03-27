from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio

from src.services.query_service.app.main import app
from src.services.query_service.app.routers.reporting import (
    ReportingService,
    get_reporting_service,
)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client():
    mock_service = AsyncMock(spec=ReportingService)
    app.dependency_overrides[get_reporting_service] = lambda: mock_service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, mock_service
    app.dependency_overrides.pop(get_reporting_service, None)


async def test_query_assets_under_management(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_assets_under_management.return_value = {
        "scope_type": "portfolio",
        "scope": {"portfolio_id": "P1", "portfolio_ids": [], "booking_center_code": None},
        "resolved_as_of_date": date(2026, 3, 27),
        "reporting_currency": "USD",
        "totals": {
            "portfolio_count": 1,
            "position_count": 2,
            "aum_reporting_currency": Decimal("150"),
        },
        "portfolios": [],
    }

    response = await client.post(
        "/reporting/assets-under-management/query",
        json={"scope": {"portfolio_id": "P1"}},
    )

    assert response.status_code == 200
    assert response.json()["reporting_currency"] == "USD"


async def test_query_asset_allocation(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_asset_allocation.return_value = {
        "scope_type": "portfolio",
        "scope": {"portfolio_id": "P1", "portfolio_ids": [], "booking_center_code": None},
        "resolved_as_of_date": date(2026, 3, 27),
        "reporting_currency": "USD",
        "total_market_value_reporting_currency": Decimal("150"),
        "views": [],
    }

    response = await client.post(
        "/reporting/asset-allocation/query",
        json={"scope": {"portfolio_id": "P1"}, "dimensions": ["asset_class"]},
    )

    assert response.status_code == 200
    assert response.json()["total_market_value_reporting_currency"] == "150"


async def test_query_cash_balances(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_cash_balances.return_value = {
        "portfolio_id": "P1",
        "portfolio_currency": "USD",
        "reporting_currency": "USD",
        "resolved_as_of_date": date(2026, 3, 27),
        "totals": {
            "cash_account_count": 1,
            "total_balance_portfolio_currency": Decimal("250"),
            "total_balance_reporting_currency": Decimal("250"),
        },
        "cash_accounts": [],
    }

    response = await client.post("/reporting/cash-balances/query", json={"portfolio_id": "P1"})

    assert response.status_code == 200
    assert response.json()["totals"]["cash_account_count"] == 1


async def test_reporting_router_maps_value_errors_to_400(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_assets_under_management.side_effect = ValueError("bad scope")

    response = await client.post(
        "/reporting/assets-under-management/query",
        json={"scope": {"portfolio_id": "P1"}},
    )

    assert response.status_code == 400
    assert "bad scope" in response.json()["detail"]
