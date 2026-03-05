from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.dtos.transaction_dto import (
    PaginatedTransactionResponse,
    TransactionRecord,
)
from src.services.query_service.app.main import app

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client():
    mock_transaction_service = MagicMock()
    mock_transaction_service.get_transactions = AsyncMock(
        return_value=PaginatedTransactionResponse(
            portfolio_id="P1",
            total=1,
            skip=0,
            limit=10,
            transactions=[
                TransactionRecord(
                    transaction_id="T1",
                    transaction_date=datetime(2025, 8, 1, 0, 0, 0),
                    transaction_type="BUY",
                    instrument_id="INST_1",
                    security_id="SEC_1",
                    quantity=10.0,
                    price=100.0,
                    gross_transaction_amount=1000.0,
                    currency="USD",
                    cash_entry_mode="EXTERNAL",
                    external_cash_transaction_id="CASH-ENTRY-2026-0001",
                )
            ],
        )
    )

    app.dependency_overrides[get_async_db_session] = lambda: AsyncMock(spec=AsyncSession)

    with patch(
        "src.services.query_service.app.routers.transactions.TransactionService",
        return_value=mock_transaction_service,
    ):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, mock_transaction_service

    app.dependency_overrides.pop(get_async_db_session, None)


async def test_get_transactions_success_with_sorting_and_filters(async_test_client):
    client, mock_service = async_test_client
    response = await client.get(
        "/portfolios/P1/transactions",
        params={
            "security_id": "SEC_1",
            "start_date": "2025-08-01",
            "end_date": "2025-08-31",
            "skip": 5,
            "limit": 20,
            "sort_by": "transaction_date",
            "sort_order": "asc",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["portfolio_id"] == "P1"
    assert payload["transactions"][0]["transaction_id"] == "T1"
    assert payload["transactions"][0]["cash_entry_mode"] == "EXTERNAL"
    assert (
        payload["transactions"][0]["external_cash_transaction_id"]
        == "CASH-ENTRY-2026-0001"
    )
    mock_service.get_transactions.assert_awaited_once_with(
        portfolio_id="P1",
        security_id="SEC_1",
        start_date=datetime(2025, 8, 1, 0, 0).date(),
        end_date=datetime(2025, 8, 31, 0, 0).date(),
        as_of_date=None,
        include_projected=False,
        skip=5,
        limit=20,
        sort_by="transaction_date",
        sort_order="asc",
    )


async def test_get_transactions_unhandled_error_is_globally_mapped(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_transactions.side_effect = RuntimeError("boom")

    response = await client.get("/portfolios/P1/transactions")

    assert response.status_code == 500
    body = response.json()
    assert body["error"] == "Internal Server Error"
    assert "correlation_id" in body


async def test_get_transactions_not_found_maps_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_transactions.side_effect = ValueError("portfolio missing")

    response = await client.get("/portfolios/P404/transactions")

    assert response.status_code == 404
    assert "portfolio missing" in response.json()["detail"].lower()


async def test_get_transactions_forwards_as_of_and_include_projected(async_test_client):
    client, mock_service = async_test_client

    response = await client.get(
        "/portfolios/P1/transactions?as_of_date=2026-02-28&include_projected=true"
    )

    assert response.status_code == 200
    mock_service.get_transactions.assert_awaited_once_with(
        portfolio_id="P1",
        security_id=None,
        start_date=None,
        end_date=None,
        as_of_date=datetime(2026, 2, 28, 0, 0).date(),
        include_projected=True,
        skip=0,
        limit=100,
        sort_by=None,
        sort_order="desc",
    )
