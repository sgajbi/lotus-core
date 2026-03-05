from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.dtos.buy_state_dto import (
    AccruedIncomeOffsetRecord,
    AccruedIncomeOffsetsResponse,
    BuyCashLinkageResponse,
    PositionLotRecord,
    PositionLotsResponse,
)
from src.services.query_service.app.main import app

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client():
    mock_buy_state_service = MagicMock()
    mock_buy_state_service.get_position_lots = AsyncMock(
        return_value=PositionLotsResponse(
            portfolio_id="PORT-1",
            security_id="US0378331005",
            lots=[
                PositionLotRecord(
                    lot_id="LOT-TXN-1",
                    source_transaction_id="TXN-1",
                    portfolio_id="PORT-1",
                    instrument_id="AAPL",
                    security_id="US0378331005",
                    acquisition_date=date(2026, 2, 28),
                    original_quantity=100,
                    open_quantity=100,
                    lot_cost_local=15005.5,
                    lot_cost_base=15005.5,
                    accrued_interest_paid_local=0,
                )
            ],
        )
    )
    mock_buy_state_service.get_accrued_offsets = AsyncMock(
        return_value=AccruedIncomeOffsetsResponse(
            portfolio_id="PORT-1",
            security_id="US0378331005",
            offsets=[
                AccruedIncomeOffsetRecord(
                    offset_id="AIO-TXN-1",
                    source_transaction_id="TXN-1",
                    portfolio_id="PORT-1",
                    instrument_id="AAPL",
                    security_id="US0378331005",
                    accrued_interest_paid_local=1250,
                    remaining_offset_local=1250,
                )
            ],
        )
    )
    mock_buy_state_service.get_buy_cash_linkage = AsyncMock(
        return_value=BuyCashLinkageResponse(
            portfolio_id="PORT-1",
            transaction_id="TXN-1",
            transaction_type="BUY",
            economic_event_id="EVT-1",
            linked_transaction_group_id="LTG-1",
            cashflow_amount=-15005.5,
            cashflow_currency="USD",
            cashflow_classification="INVESTMENT_OUTFLOW",
        )
    )

    app.dependency_overrides[get_async_db_session] = lambda: AsyncMock(spec=AsyncSession)
    with patch(
        "src.services.query_service.app.routers.buy_state.BuyStateService",
        return_value=mock_buy_state_service,
    ):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, mock_buy_state_service
    app.dependency_overrides.pop(get_async_db_session, None)


async def test_get_position_lots_success(async_test_client):
    client, mock_service = async_test_client
    response = await client.get("/portfolios/PORT-1/positions/US0378331005/lots")
    assert response.status_code == 200
    payload = response.json()
    assert payload["portfolio_id"] == "PORT-1"
    assert payload["lots"][0]["lot_id"] == "LOT-TXN-1"
    mock_service.get_position_lots.assert_awaited_once_with(
        portfolio_id="PORT-1", security_id="US0378331005"
    )


async def test_get_accrued_offsets_success(async_test_client):
    client, mock_service = async_test_client
    response = await client.get("/portfolios/PORT-1/positions/US0378331005/accrued-offsets")
    assert response.status_code == 200
    payload = response.json()
    assert payload["offsets"][0]["offset_id"] == "AIO-TXN-1"
    mock_service.get_accrued_offsets.assert_awaited_once_with(
        portfolio_id="PORT-1", security_id="US0378331005"
    )


async def test_get_cash_linkage_not_found(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_buy_cash_linkage.side_effect = ValueError("not found")
    response = await client.get("/portfolios/PORT-1/transactions/T404/cash-linkage")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


async def test_get_cash_linkage_success(async_test_client):
    client, mock_service = async_test_client
    response = await client.get("/portfolios/PORT-1/transactions/TXN-1/cash-linkage")
    assert response.status_code == 200
    payload = response.json()
    assert payload["transaction_id"] == "TXN-1"
    assert payload["cashflow_classification"] == "INVESTMENT_OUTFLOW"
    mock_service.get_buy_cash_linkage.assert_awaited_with(
        portfolio_id="PORT-1", transaction_id="TXN-1"
    )


async def test_get_position_lots_not_found(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_position_lots.side_effect = ValueError("portfolio missing")
    response = await client.get("/portfolios/P404/positions/US0378331005/lots")
    assert response.status_code == 404
    assert "portfolio missing" in response.json()["detail"]
