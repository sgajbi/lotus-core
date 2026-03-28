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
        "look_through": {
            "requested_mode": "direct_only",
            "applied_mode": "direct_only",
            "supported": False,
            "decomposed_position_count": 0,
            "limitation_reason": None,
        },
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


async def test_query_portfolio_summary(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_portfolio_summary.return_value = {
        "portfolio_id": "P1",
        "booking_center_code": "SGPB",
        "client_id": "CIF-1",
        "portfolio_currency": "USD",
        "reporting_currency": "USD",
        "resolved_as_of_date": date(2026, 3, 27),
        "portfolio_type": "DISCRETIONARY",
        "objective": "Growth",
        "risk_exposure": "BALANCED",
        "status": "ACTIVE",
        "totals": {
            "total_market_value_portfolio_currency": Decimal("1000"),
            "total_market_value_reporting_currency": Decimal("1000"),
            "cash_balance_portfolio_currency": Decimal("200"),
            "cash_balance_reporting_currency": Decimal("200"),
            "invested_market_value_portfolio_currency": Decimal("800"),
            "invested_market_value_reporting_currency": Decimal("800"),
        },
        "snapshot_metadata": {
            "snapshot_date": date(2026, 3, 27),
            "position_count": 2,
            "cash_account_count": 1,
            "valued_position_count": 1,
            "unvalued_position_count": 1,
        },
    }

    response = await client.post("/reporting/portfolio-summary/query", json={"portfolio_id": "P1"})

    assert response.status_code == 200
    assert response.json()["totals"]["cash_balance_portfolio_currency"] == "200"


async def test_query_holdings_snapshot(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_holdings_snapshot.return_value = {
        "portfolio_id": "P1",
        "portfolio_currency": "USD",
        "reporting_currency": "USD",
        "resolved_as_of_date": date(2026, 3, 27),
        "snapshot_date": date(2026, 3, 27),
        "total_market_value_portfolio_currency": Decimal("1000"),
        "total_market_value_reporting_currency": Decimal("1000"),
        "positions": [
            {
                "security_id": "SEC1",
                "instrument_name": "Apple Inc.",
                "asset_class": "EQUITY",
                "sector": "TECH",
                "country": "US",
                "region": "North America",
                "account_currency": "USD",
                "quantity": Decimal("10"),
                "market_value_portfolio_currency": Decimal("1000"),
                "market_value_reporting_currency": Decimal("1000"),
                "weight": Decimal("1"),
                "valuation_status": "VALUED",
            }
        ],
    }

    response = await client.post("/reporting/holdings-snapshot/query", json={"portfolio_id": "P1"})

    assert response.status_code == 200
    assert response.json()["positions"][0]["region"] == "North America"


async def test_reporting_router_maps_value_errors_to_400(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_assets_under_management.side_effect = ValueError("bad scope")

    response = await client.post(
        "/reporting/assets-under-management/query",
        json={"scope": {"portfolio_id": "P1"}},
    )

    assert response.status_code == 400
    assert "bad scope" in response.json()["detail"]


async def test_query_income_summary(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_income_summary.return_value = {
        "scope_type": "portfolio",
        "scope": {"portfolio_id": "P1", "portfolio_ids": [], "booking_center_code": None},
        "resolved_window": {"start_date": date(2026, 3, 1), "end_date": date(2026, 3, 27)},
        "reporting_currency": "USD",
        "totals": {
            "portfolio_count": 1,
            "requested_window": {
                "transaction_count": 2,
                "gross_amount_portfolio_currency": Decimal("80"),
                "gross_amount_reporting_currency": Decimal("80"),
                "withholding_tax_portfolio_currency": Decimal("3"),
                "withholding_tax_reporting_currency": Decimal("3"),
                "other_deductions_portfolio_currency": Decimal("1"),
                "other_deductions_reporting_currency": Decimal("1"),
                "net_amount_portfolio_currency": Decimal("76"),
                "net_amount_reporting_currency": Decimal("76"),
            },
            "year_to_date": {
                "transaction_count": 3,
                "gross_amount_portfolio_currency": Decimal("110"),
                "gross_amount_reporting_currency": Decimal("110"),
                "withholding_tax_portfolio_currency": Decimal("3"),
                "withholding_tax_reporting_currency": Decimal("3"),
                "other_deductions_portfolio_currency": Decimal("1"),
                "other_deductions_reporting_currency": Decimal("1"),
                "net_amount_portfolio_currency": Decimal("106"),
                "net_amount_reporting_currency": Decimal("106"),
            },
        },
        "portfolios": [],
    }

    response = await client.post(
        "/reporting/income-summary/query",
        json={
            "scope": {"portfolio_id": "P1"},
            "window": {"start_date": "2026-03-01", "end_date": "2026-03-27"},
        },
    )

    assert response.status_code == 200
    assert response.json()["totals"]["requested_window"]["net_amount_reporting_currency"] == "76"


async def test_query_activity_summary(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_activity_summary.return_value = {
        "scope_type": "portfolio",
        "scope": {"portfolio_id": "P1", "portfolio_ids": [], "booking_center_code": None},
        "resolved_window": {"start_date": date(2026, 3, 1), "end_date": date(2026, 3, 27)},
        "reporting_currency": "USD",
        "totals": {
            "portfolio_count": 1,
            "buckets": [
                {
                    "bucket": "INFLOWS",
                    "requested_window": {
                        "transaction_count": 1,
                        "amount_portfolio_currency": Decimal("1000"),
                        "amount_reporting_currency": Decimal("1000"),
                    },
                    "year_to_date": {
                        "transaction_count": 2,
                        "amount_portfolio_currency": Decimal("1500"),
                        "amount_reporting_currency": Decimal("1500"),
                    },
                }
            ],
        },
        "portfolios": [],
    }

    response = await client.post(
        "/reporting/activity-summary/query",
        json={
            "scope": {"portfolio_id": "P1"},
            "window": {"start_date": "2026-03-01", "end_date": "2026-03-27"},
        },
    )

    assert response.status_code == 200
    assert response.json()["totals"]["buckets"][0]["bucket"] == "INFLOWS"
