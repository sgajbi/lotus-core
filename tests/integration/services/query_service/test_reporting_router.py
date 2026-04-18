from datetime import UTC, date, datetime
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


def _runtime_metadata(as_of_date: date) -> dict:
    return {
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


async def test_reporting_router_maps_value_errors_to_400(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_assets_under_management.side_effect = ValueError("bad scope")

    response = await client.post(
        "/reporting/assets-under-management/query",
        json={"scope": {"portfolio_id": "P1"}},
    )

    assert response.status_code == 400
    assert "bad scope" in response.json()["detail"]


async def test_get_reporting_service_wraps_db_session():
    db = object()
    service = get_reporting_service(db)  # type: ignore[arg-type]

    assert isinstance(service, ReportingService)
    assert service.repo.db is db


@pytest.mark.parametrize(
    ("path", "payload", "method_name", "error_detail", "exception_type", "status_code"),
    [
        (
            "/reporting/asset-allocation/query",
            {"scope": {"portfolio_id": "P1"}, "dimensions": ["asset_class"]},
            "get_asset_allocation",
            "bad allocation scope",
            ValueError,
            400,
        ),
        (
            "/reporting/portfolio-summary/query",
            {"portfolio_id": "P1"},
            "get_portfolio_summary",
            "bad snapshot request",
            ValueError,
            400,
        ),
        (
            "/reporting/portfolio-summary/query",
            {"portfolio_id": "P404"},
            "get_portfolio_summary",
            "Portfolio with id P404 not found",
            LookupError,
            404,
        ),
    ],
)
async def test_reporting_router_maps_all_query_value_errors_to_400(
    async_test_client,
    path: str,
    payload: dict,
    method_name: str,
    error_detail: str,
    exception_type: type[Exception],
    status_code: int,
):
    client, mock_service = async_test_client
    getattr(mock_service, method_name).side_effect = exception_type(error_detail)

    response = await client.post(path, json=payload)

    assert response.status_code == status_code
    assert response.json()["detail"] == error_detail
