from datetime import date
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.dtos.source_data_product_identity import (
    source_data_product_runtime_metadata,
)
from src.services.query_service.app.main import app
from src.services.query_service.app.routers.positions import PositionService, get_position_service

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client():
    mock_service = AsyncMock()
    app.dependency_overrides[get_position_service] = lambda: mock_service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, mock_service
    app.dependency_overrides.pop(get_position_service, None)


async def test_get_position_history_success(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_position_history.return_value = {
        "portfolio_id": "P1",
        "security_id": "S1",
        "positions": [
            {
                "position_date": date(2025, 1, 1),
                "transaction_id": "T1",
                "quantity": 10.0,
                "cost_basis": 1000.0,
                "cost_basis_local": 1000.0,
                "valuation": None,
                "reprocessing_status": "CURRENT",
            }
        ],
    }

    response = await client.get("/portfolios/P1/position-history?security_id=S1")

    assert response.status_code == 200
    assert response.json()["security_id"] == "S1"
    assert "X-Correlation-ID" in response.headers


async def test_get_position_history_unexpected_maps_to_500(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_position_history.side_effect = RuntimeError("boom")

    response = await client.get("/portfolios/P1/position-history?security_id=S1")

    assert response.status_code == 500
    assert "unexpected error" in response.json()["detail"].lower()


async def test_get_latest_positions_success(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_portfolio_positions.return_value = {
        "portfolio_id": "P1",
        "positions": [
            {
                "security_id": "S1",
                "quantity": 15.0,
                "instrument_name": "A",
                "position_date": date(2025, 1, 1),
                "asset_class": "Equity",
                "cost_basis": 1300.0,
                "cost_basis_local": 1300.0,
                "valuation": None,
                "reprocessing_status": "CURRENT",
            }
        ],
        **source_data_product_runtime_metadata(as_of_date=date(2025, 1, 1)),
    }

    response = await client.get("/portfolios/P1/positions")

    assert response.status_code == 200
    payload = response.json()
    assert payload["portfolio_id"] == "P1"
    assert payload["product_name"] == "HoldingsAsOf"
    assert payload["product_version"] == "v1"
    assert payload["as_of_date"] == "2025-01-01"
    assert payload["generated_at"]
    mock_service.get_portfolio_positions.assert_awaited_once_with(
        portfolio_id="P1",
        as_of_date=None,
        include_projected=False,
    )


async def test_get_latest_positions_unexpected_maps_to_500(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_portfolio_positions.side_effect = RuntimeError("boom")

    response = await client.get("/portfolios/P1/positions")

    assert response.status_code == 500
    assert "unexpected error" in response.json()["detail"].lower()


async def test_get_position_history_not_found_maps_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_position_history.side_effect = ValueError("not found")

    response = await client.get("/portfolios/P404/position-history?security_id=S1")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


async def test_get_latest_positions_not_found_maps_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_portfolio_positions.side_effect = ValueError("not found")

    response = await client.get("/portfolios/P404/positions")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


async def test_get_latest_positions_forwards_as_of_and_include_projected(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_portfolio_positions.return_value = {
        "portfolio_id": "P1",
        "positions": [],
        **source_data_product_runtime_metadata(as_of_date=date(2026, 2, 28)),
    }

    response = await client.get(
        "/portfolios/P1/positions?as_of_date=2026-02-28&include_projected=true"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["product_name"] == "HoldingsAsOf"
    assert payload["as_of_date"] == "2026-02-28"
    mock_service.get_portfolio_positions.assert_awaited_once_with(
        portfolio_id="P1",
        as_of_date=date(2026, 2, 28),
        include_projected=True,
    )


async def test_get_position_service_dependency_factory():
    db = AsyncMock(spec=AsyncSession)

    service = get_position_service(db)

    assert isinstance(service, PositionService)
