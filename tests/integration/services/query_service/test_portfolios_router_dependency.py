from datetime import date
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.main import app
from src.services.query_service.app.routers.portfolios import (
    PortfolioService,
    get_portfolio_service,
)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client():
    mock_service = AsyncMock()
    app.dependency_overrides[get_portfolio_service] = lambda: mock_service
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, mock_service
    app.dependency_overrides.pop(get_portfolio_service, None)


async def test_get_portfolios_success(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_portfolios.return_value = {
        "portfolios": [
            {
                "portfolio_id": "P1",
                "base_currency": "USD",
                "open_date": date(2025, 1, 1),
                "close_date": None,
                "risk_exposure": "MODERATE",
                "investment_time_horizon": "LONG_TERM",
                "portfolio_type": "DISCRETIONARY",
                "objective": "GROWTH",
                "booking_center_code": "LON-01",
                "client_id": "CIF-1",
                "is_leverage_allowed": False,
                "advisor_id": "ADV-1",
                "status": "ACTIVE",
                "cost_basis_method": "FIFO",
            }
        ]
    }

    response = await client.get("/portfolios/")

    assert response.status_code == 200
    assert response.json()["portfolios"][0]["portfolio_id"] == "P1"
    assert response.json()["portfolios"][0]["cost_basis_method"] == "FIFO"
    assert "X-Correlation-ID" in response.headers


async def test_get_portfolios_unexpected_maps_to_500(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_portfolios.side_effect = RuntimeError("boom")

    response = await client.get("/portfolios/")

    assert response.status_code == 500
    assert response.json()["error"] == "Internal Server Error"
    assert "correlation_id" in response.json()


async def test_get_portfolio_by_id_success(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_portfolio_by_id.return_value = {
        "portfolio_id": "P2",
        "base_currency": "USD",
        "open_date": date(2025, 1, 1),
        "close_date": None,
        "risk_exposure": "MODERATE",
        "investment_time_horizon": "LONG_TERM",
        "portfolio_type": "DISCRETIONARY",
        "objective": "GROWTH",
        "booking_center_code": "LON-01",
        "client_id": "CIF-2",
        "is_leverage_allowed": False,
        "advisor_id": "ADV-2",
        "status": "ACTIVE",
        "cost_basis_method": "FIFO",
    }

    response = await client.get("/portfolios/P2")

    assert response.status_code == 200
    assert response.json()["portfolio_id"] == "P2"


async def test_get_portfolio_by_id_not_found_maps_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_portfolio_by_id.side_effect = LookupError("not found")

    response = await client.get("/portfolios/P404")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


async def test_get_portfolio_service_dependency_factory():
    db = AsyncMock(spec=AsyncSession)

    service = get_portfolio_service(db)

    assert isinstance(service, PortfolioService)


async def test_get_portfolios_forwards_portfolio_ids(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_portfolios.return_value = {"portfolios": []}

    response = await client.get(
        "/portfolios/",
        params=[("portfolio_ids", "P1"), ("portfolio_ids", "P2")],
    )

    assert response.status_code == 200
    mock_service.get_portfolios.assert_awaited_once_with(
        portfolio_id=None,
        portfolio_ids=["P1", "P2"],
        client_id=None,
        booking_center_code=None,
    )


async def test_get_portfolios_forwards_discovery_filters(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_portfolios.return_value = {"portfolios": []}

    response = await client.get(
        "/portfolios/",
        params={
            "portfolio_id": "P1",
            "client_id": "CIF-1",
            "booking_center_code": "SGPB",
        },
    )

    assert response.status_code == 200
    mock_service.get_portfolios.assert_awaited_once_with(
        portfolio_id="P1",
        portfolio_ids=None,
        client_id="CIF-1",
        booking_center_code="SGPB",
    )
