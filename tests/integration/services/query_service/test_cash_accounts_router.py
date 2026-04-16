from datetime import date
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio

from src.services.query_service.app.main import app
from src.services.query_service.app.routers.cash_accounts import (
    CashAccountService,
    get_cash_account_service,
)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client():
    mock_service = AsyncMock(spec=CashAccountService)
    app.dependency_overrides[get_cash_account_service] = lambda: mock_service
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, mock_service
    app.dependency_overrides.pop(get_cash_account_service, None)


async def test_get_cash_accounts(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_cash_accounts.return_value = {
        "portfolio_id": "P1",
        "resolved_as_of_date": date(2026, 3, 27),
        "cash_accounts": [
            {
                "cash_account_id": "CASH-ACC-USD-001",
                "portfolio_id": "P1",
                "security_id": "CASH_USD",
                "display_name": "USD Operating Cash",
                "account_currency": "USD",
                "account_role": "OPERATING_CASH",
                "lifecycle_status": "ACTIVE",
                "opened_on": date(2026, 1, 1),
                "closed_on": None,
                "source_system": "lotus-manage",
            }
        ],
    }

    response = await client.get("/portfolios/P1/cash-accounts", params={"as_of_date": "2026-03-27"})

    assert response.status_code == 200
    assert response.json()["cash_accounts"][0]["cash_account_id"] == "CASH-ACC-USD-001"
    mock_service.get_cash_accounts.assert_awaited_once_with(
        "P1", as_of_date=date(2026, 3, 27)
    )


async def test_get_cash_accounts_without_as_of_date_forwards_none(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_cash_accounts.return_value = {
        "portfolio_id": "P1",
        "resolved_as_of_date": None,
        "cash_accounts": [],
    }

    response = await client.get("/portfolios/P1/cash-accounts")

    assert response.status_code == 200
    assert response.json()["resolved_as_of_date"] is None
    mock_service.get_cash_accounts.assert_awaited_once_with("P1", as_of_date=None)


async def test_get_cash_accounts_maps_missing_portfolio_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_cash_accounts.side_effect = ValueError("Portfolio with id P404 not found")

    response = await client.get("/portfolios/P404/cash-accounts")

    assert response.status_code == 404
    assert response.json()["detail"] == "Portfolio with id P404 not found"


async def test_get_cash_accounts_unexpected_uses_global_500_envelope(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_cash_accounts.side_effect = RuntimeError("boom")

    response = await client.get("/portfolios/P1/cash-accounts")

    assert response.status_code == 500
    assert response.json()["error"] == "Internal Server Error"
    assert "correlation_id" in response.json()
