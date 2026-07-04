from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio

from src.services.query_service.app.dependencies import (
    get_instrument_service,
    get_portfolio_service,
)
from src.services.query_service.app.main import app

pytestmark = pytest.mark.asyncio


def _assert_lookup_items_contract(items: list[dict]) -> None:
    assert isinstance(items, list)
    for item in items:
        assert isinstance(item.get("id"), str)
        assert item["id"].strip() != ""
        assert isinstance(item.get("label"), str)
        assert item["label"].strip() != ""


@pytest_asyncio.fixture
async def async_test_client():
    mock_portfolio_service = MagicMock()
    mock_instrument_service = MagicMock()
    mock_portfolio_service.get_portfolios = AsyncMock()
    mock_portfolio_service.search_portfolio_lookup_items = AsyncMock(return_value=[])
    mock_portfolio_service.list_currency_lookup_items = AsyncMock(return_value=[])
    mock_instrument_service.get_instruments = AsyncMock()
    mock_instrument_service.search_instrument_lookup_items = AsyncMock(return_value=[])
    mock_instrument_service.list_currency_lookup_items = AsyncMock(return_value=[])

    app.dependency_overrides[get_portfolio_service] = lambda: mock_portfolio_service
    app.dependency_overrides[get_instrument_service] = lambda: mock_instrument_service

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, mock_portfolio_service, mock_instrument_service

    app.dependency_overrides.pop(get_portfolio_service, None)
    app.dependency_overrides.pop(get_instrument_service, None)


async def test_portfolio_lookup_contract_sorted_filtered_and_limited(async_test_client):
    client, mock_portfolio_service, _ = async_test_client
    mock_portfolio_service.search_portfolio_lookup_items.return_value = [
        {"id": "PF_10", "label": "PF_10"},
        {"id": "PF_20", "label": "PF_20"},
    ]

    response = await client.get("/lookups/portfolios?q=PF_&limit=2")

    assert response.status_code == 200
    items = response.json()["items"]
    _assert_lookup_items_contract(items)
    assert items == [
        {"id": "PF_10", "label": "PF_10"},
        {"id": "PF_20", "label": "PF_20"},
    ]
    mock_portfolio_service.search_portfolio_lookup_items.assert_awaited_once_with(
        client_id=None,
        booking_center_code=None,
        q="PF_",
        limit=2,
    )
    mock_portfolio_service.get_portfolios.assert_not_awaited()


async def test_instrument_lookup_contract_with_q_filter(async_test_client):
    client, _, mock_instrument_service = async_test_client
    mock_instrument_service.search_instrument_lookup_items.return_value = [
        {"id": "SEC_A", "label": "SEC_A | Alpha Instrument"}
    ]

    response = await client.get("/lookups/instruments?limit=200&product_type=Equity&q=alpha")

    assert response.status_code == 200
    items = response.json()["items"]
    _assert_lookup_items_contract(items)
    assert items == [{"id": "SEC_A", "label": "SEC_A | Alpha Instrument"}]
    mock_instrument_service.search_instrument_lookup_items.assert_awaited_once_with(
        product_type="Equity",
        q="alpha",
        limit=200,
    )
    mock_instrument_service.get_instruments.assert_not_awaited()


async def test_currency_lookup_contract_source_scope_and_uppercase(async_test_client):
    client, mock_portfolio_service, mock_instrument_service = async_test_client
    mock_instrument_service.list_currency_lookup_items.return_value = [
        {"id": "USD", "label": "USD"}
    ]

    response = await client.get("/lookups/currencies?source=INSTRUMENTS&q=US&limit=5")

    assert response.status_code == 200
    items = response.json()["items"]
    _assert_lookup_items_contract(items)
    assert items == [{"id": "USD", "label": "USD"}]
    mock_instrument_service.list_currency_lookup_items.assert_awaited_once_with(q="US", limit=5)
    mock_instrument_service.get_instruments.assert_not_awaited()
    mock_portfolio_service.list_currency_lookup_items.assert_not_awaited()
    mock_portfolio_service.get_portfolios.assert_not_awaited()


async def test_currency_lookup_contract_all_merges_bounded_source_queries(async_test_client):
    client, mock_portfolio_service, mock_instrument_service = async_test_client
    mock_portfolio_service.list_currency_lookup_items.return_value = [
        {"id": "USD", "label": "USD"},
        {"id": "CHF", "label": "CHF"},
    ]
    mock_instrument_service.list_currency_lookup_items.return_value = [
        {"id": "USD", "label": "USD"},
        {"id": "EUR", "label": "EUR"},
    ]

    response = await client.get("/lookups/currencies?source=ALL&limit=2")

    assert response.status_code == 200
    assert response.json()["items"] == [
        {"id": "CHF", "label": "CHF"},
        {"id": "EUR", "label": "EUR"},
    ]
    mock_portfolio_service.list_currency_lookup_items.assert_awaited_once_with(q=None, limit=2)
    mock_instrument_service.list_currency_lookup_items.assert_awaited_once_with(q=None, limit=2)
    mock_portfolio_service.get_portfolios.assert_not_awaited()
    mock_instrument_service.get_instruments.assert_not_awaited()


async def test_lookup_contract_unexpected_errors_use_global_500_envelope(async_test_client):
    client, mock_portfolio_service, _ = async_test_client
    mock_portfolio_service.search_portfolio_lookup_items.side_effect = RuntimeError("boom")

    response = await client.get("/lookups/portfolios")

    assert response.status_code == 500
    assert response.json()["error"] == "Internal Server Error"
    assert "correlation_id" in response.json()
