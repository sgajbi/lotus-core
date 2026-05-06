from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio

from src.services.query_service.app.main import app
from src.services.query_service.app.routers.cashflow_projection import (
    get_cashflow_projection_service,
)

pytestmark = pytest.mark.asyncio


def _source_metadata(as_of_date: date) -> dict[str, object]:
    return {
        "generated_at": datetime(2026, 3, 1, 1, 5, tzinfo=UTC),
        "data_quality_status": "COMPLETE",
        "latest_evidence_timestamp": datetime(2026, 3, 1, 1, 4, tzinfo=UTC),
        "source_batch_fingerprint": f"cashflow_projection:P1:{as_of_date}:fixture",
    }


@pytest_asyncio.fixture
async def async_test_client():
    mock_service = AsyncMock()
    app.dependency_overrides[get_cashflow_projection_service] = lambda: mock_service
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, mock_service
    app.dependency_overrides.pop(get_cashflow_projection_service, None)


async def test_cashflow_projection_success(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_cashflow_projection.return_value = {
        **_source_metadata(date(2026, 3, 1)),
        "portfolio_id": "P1",
        "as_of_date": date(2026, 3, 1),
        "range_start_date": date(2026, 3, 1),
        "range_end_date": date(2026, 3, 11),
        "include_projected": True,
        "portfolio_currency": "USD",
        "points": [],
        "total_net_cashflow": 0,
        "projection_days": 10,
        "notes": "Projected window includes settlement-dated future external cash movements.",
    }

    response = await client.get("/portfolios/P1/cashflow-projection")

    assert response.status_code == 200
    mock_service.get_cashflow_projection.assert_awaited_once_with(
        portfolio_id="P1",
        horizon_days=10,
        as_of_date=None,
        include_projected=True,
    )


async def test_cashflow_projection_forwards_params(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_cashflow_projection.return_value = {
        **_source_metadata(date(2026, 3, 1)),
        "portfolio_id": "P1",
        "as_of_date": date(2026, 3, 1),
        "range_start_date": date(2026, 3, 1),
        "range_end_date": date(2026, 3, 6),
        "include_projected": False,
        "portfolio_currency": "USD",
        "points": [],
        "total_net_cashflow": 0,
        "projection_days": 5,
        "notes": "Booked-only view capped at as_of_date.",
    }

    response = await client.get(
        "/portfolios/P1/cashflow-projection?horizon_days=5&as_of_date=2026-03-01&include_projected=false"
    )

    assert response.status_code == 200
    mock_service.get_cashflow_projection.assert_awaited_once_with(
        portfolio_id="P1",
        horizon_days=5,
        as_of_date=date(2026, 3, 1),
        include_projected=False,
    )


async def test_cashflow_projection_not_found_maps_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_cashflow_projection.side_effect = ValueError("not found")

    response = await client.get("/portfolios/P404/cashflow-projection")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


async def test_cashflow_projection_unexpected_uses_global_500_envelope(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_cashflow_projection.side_effect = RuntimeError("boom")

    response = await client.get("/portfolios/P1/cashflow-projection")

    assert response.status_code == 500
    assert response.json()["error"] == "Internal Server Error"
    assert "correlation_id" in response.json()
