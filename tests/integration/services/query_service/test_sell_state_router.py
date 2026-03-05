from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.dtos.sell_state_dto import (
    SellCashLinkageResponse,
    SellDisposalRecord,
    SellDisposalsResponse,
)
from src.services.query_service.app.main import app

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client():
    mock_sell_state_service = MagicMock()
    mock_sell_state_service.get_sell_disposals = AsyncMock(
        return_value=SellDisposalsResponse(
            portfolio_id="PORT-1",
            security_id="US0378331005",
            sell_disposals=[
                SellDisposalRecord(
                    transaction_id="TXN-SELL-1",
                    transaction_date=datetime(2026, 3, 1, 9, 30),
                    instrument_id="AAPL",
                    security_id="US0378331005",
                    quantity_disposed=Decimal("25"),
                    disposal_cost_basis_base=Decimal("3750"),
                    disposal_cost_basis_local=Decimal("3750"),
                    net_sell_proceeds_base=Decimal("4250"),
                    net_sell_proceeds_local=Decimal("4250"),
                    realized_gain_loss_base=Decimal("500"),
                    realized_gain_loss_local=Decimal("500"),
                    economic_event_id="EVT-SELL-PORT-1-TXN-SELL-1",
                    linked_transaction_group_id="LTG-SELL-PORT-1-TXN-SELL-1",
                    calculation_policy_id="SELL_FIFO_POLICY",
                    calculation_policy_version="1.0.0",
                    source_system="OMS_PRIMARY",
                )
            ],
        )
    )
    mock_sell_state_service.get_sell_cash_linkage = AsyncMock(
        return_value=SellCashLinkageResponse(
            portfolio_id="PORT-1",
            transaction_id="TXN-SELL-1",
            transaction_type="SELL",
            economic_event_id="EVT-SELL-PORT-1-TXN-SELL-1",
            linked_transaction_group_id="LTG-SELL-PORT-1-TXN-SELL-1",
            calculation_policy_id="SELL_FIFO_POLICY",
            calculation_policy_version="1.0.0",
            cashflow_date=datetime(2026, 3, 3, 0, 0),
            cashflow_amount=Decimal("4250"),
            cashflow_currency="USD",
            cashflow_classification="INVESTMENT_INFLOW",
        )
    )

    app.dependency_overrides[get_async_db_session] = lambda: AsyncMock(spec=AsyncSession)

    with patch(
        "src.services.query_service.app.routers.sell_state.SellStateService",
        return_value=mock_sell_state_service,
    ):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, mock_sell_state_service

    app.dependency_overrides.pop(get_async_db_session, None)


async def test_get_sell_disposals_success(async_test_client):
    client, mock_service = async_test_client

    response = await client.get("/portfolios/PORT-1/positions/US0378331005/sell-disposals")

    assert response.status_code == 200
    payload = response.json()
    assert payload["sell_disposals"][0]["transaction_id"] == "TXN-SELL-1"
    mock_service.get_sell_disposals.assert_awaited_once_with(
        portfolio_id="PORT-1", security_id="US0378331005"
    )


async def test_get_sell_cash_linkage_success(async_test_client):
    client, mock_service = async_test_client

    response = await client.get("/portfolios/PORT-1/transactions/TXN-SELL-1/sell-cash-linkage")

    assert response.status_code == 200
    payload = response.json()
    assert payload["cashflow_classification"] == "INVESTMENT_INFLOW"
    mock_service.get_sell_cash_linkage.assert_awaited_once_with(
        portfolio_id="PORT-1", transaction_id="TXN-SELL-1"
    )


async def test_get_sell_cash_linkage_not_found(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_sell_cash_linkage.side_effect = ValueError("transaction missing")

    response = await client.get("/portfolios/PORT-1/transactions/T404/sell-cash-linkage")

    assert response.status_code == 404
    assert "transaction missing" in response.json()["detail"].lower()


async def test_get_sell_disposals_not_found(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_sell_disposals.side_effect = ValueError("portfolio missing")

    response = await client.get("/portfolios/P404/positions/US0378331005/sell-disposals")

    assert response.status_code == 404
    assert "portfolio missing" in response.json()["detail"].lower()
