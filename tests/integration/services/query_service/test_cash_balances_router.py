from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio

from src.services.query_service.app.main import app
from src.services.query_service.app.routers.cash_balances import (
    CashBalanceService,
    get_cash_balance_service,
)

pytestmark = pytest.mark.asyncio


def _runtime_metadata(as_of_date: date) -> dict:
    return {
        "product_name": "HoldingsAsOf",
        "product_version": "v1",
        "generated_at": datetime(2026, 3, 27, 12, 0, tzinfo=UTC),
        "as_of_date": as_of_date,
        "restatement_version": "current",
        "reconciliation_status": "UNKNOWN",
        "data_quality_status": "UNKNOWN",
        "latest_evidence_timestamp": None,
        "source_batch_fingerprint": None,
        "snapshot_id": None,
        "tenant_id": None,
        "policy_version": None,
        "correlation_id": None,
    }


@pytest_asyncio.fixture
async def async_test_client():
    mock_service = AsyncMock(spec=CashBalanceService)
    app.dependency_overrides[get_cash_balance_service] = lambda: mock_service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, mock_service
    app.dependency_overrides.pop(get_cash_balance_service, None)


async def test_get_cash_balances(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_cash_balances.return_value = {
        "portfolio_id": "P1",
        "portfolio_currency": "USD",
        "reporting_currency": "SGD",
        "resolved_as_of_date": date(2026, 3, 27),
        "totals": {
            "cash_account_count": 1,
            "total_balance_portfolio_currency": Decimal("250"),
            "total_balance_reporting_currency": Decimal("300"),
        },
        "cash_accounts": [],
        **_runtime_metadata(date(2026, 3, 27)),
    }

    response = await client.get(
        "/portfolios/P1/cash-balances",
        params={"as_of_date": "2026-03-27", "reporting_currency": "SGD"},
    )

    assert response.status_code == 200
    assert response.json()["product_name"] == "HoldingsAsOf"
    mock_service.get_cash_balances.assert_awaited_once_with(
        portfolio_id="P1",
        as_of_date=date(2026, 3, 27),
        reporting_currency="SGD",
    )


async def test_get_cash_balances_defaults_optional_query_params(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_cash_balances.return_value = {
        "portfolio_id": "P1",
        "portfolio_currency": "USD",
        "reporting_currency": "USD",
        "resolved_as_of_date": date(2026, 3, 27),
        "totals": {
            "cash_account_count": 0,
            "total_balance_portfolio_currency": Decimal("0"),
            "total_balance_reporting_currency": Decimal("0"),
        },
        "cash_accounts": [],
        **_runtime_metadata(date(2026, 3, 27)),
    }

    response = await client.get("/portfolios/P1/cash-balances")

    assert response.status_code == 200
    mock_service.get_cash_balances.assert_awaited_once_with(
        portfolio_id="P1",
        as_of_date=None,
        reporting_currency=None,
    )


async def test_get_cash_balances_maps_missing_portfolio_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_cash_balances.side_effect = ValueError("Portfolio with id P404 not found")

    response = await client.get("/portfolios/P404/cash-balances")

    assert response.status_code == 404
    assert response.json()["detail"] == "Portfolio with id P404 not found"


async def test_get_cash_balances_maps_other_resolution_errors_to_400(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_cash_balances.side_effect = ValueError(
        "No business date is available for cash balance queries."
    )

    response = await client.get("/portfolios/P1/cash-balances")

    assert response.status_code == 400
    assert response.json()["detail"] == "No business date is available for cash balance queries."
