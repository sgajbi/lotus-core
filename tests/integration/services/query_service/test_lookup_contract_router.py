from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.dtos.instrument_dto import PaginatedInstrumentResponse
from src.services.query_service.app.dtos.portfolio_dto import PortfolioQueryResponse
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
    mock_instrument_service.get_instruments = AsyncMock()

    app.dependency_overrides[get_async_db_session] = lambda: AsyncMock(spec=AsyncSession)

    with (
        patch(
            "src.services.query_service.app.routers.lookups.PortfolioService",
            return_value=mock_portfolio_service,
        ),
        patch(
            "src.services.query_service.app.routers.lookups.InstrumentService",
            return_value=mock_instrument_service,
        ),
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, mock_portfolio_service, mock_instrument_service

    app.dependency_overrides.pop(get_async_db_session, None)


async def test_portfolio_lookup_contract_sorted_filtered_and_limited(async_test_client):
    client, mock_portfolio_service, _ = async_test_client
    mock_portfolio_service.get_portfolios.return_value = PortfolioQueryResponse(
        portfolios=[
            {
                "portfolio_id": "PF_20",
                "base_currency": "USD",
                "open_date": "2025-01-01",
                "close_date": None,
                "risk_exposure": "MODERATE",
                "investment_time_horizon": "LONG_TERM",
                "portfolio_type": "DISCRETIONARY",
                "objective": "GROWTH",
                "booking_center_code": "LON-01",
                "client_id": "CIF-1",
                "is_leverage_allowed": False,
                "advisor_id": "ADV-1",
                "status": "ACTIVE",
            },
            {
                "portfolio_id": "AF_01",
                "base_currency": "USD",
                "open_date": "2025-01-01",
                "close_date": None,
                "risk_exposure": "MODERATE",
                "investment_time_horizon": "LONG_TERM",
                "portfolio_type": "DISCRETIONARY",
                "objective": "GROWTH",
                "booking_center_code": "LON-01",
                "client_id": "CIF-1",
                "is_leverage_allowed": False,
                "advisor_id": "ADV-1",
                "status": "ACTIVE",
            },
            {
                "portfolio_id": "PF_10",
                "base_currency": "USD",
                "open_date": "2025-01-01",
                "close_date": None,
                "risk_exposure": "MODERATE",
                "investment_time_horizon": "LONG_TERM",
                "portfolio_type": "DISCRETIONARY",
                "objective": "GROWTH",
                "booking_center_code": "LON-01",
                "client_id": "CIF-1",
                "is_leverage_allowed": False,
                "advisor_id": "ADV-1",
                "status": "ACTIVE",
            },
        ]
    )

    response = await client.get("/lookups/portfolios?q=PF_&limit=2")
    assert response.status_code == 200
    items = response.json()["items"]
    _assert_lookup_items_contract(items)
    assert items == [
        {"id": "PF_10", "label": "PF_10"},
        {"id": "PF_20", "label": "PF_20"},
    ]


async def test_instrument_lookup_contract_with_q_filter(async_test_client):
    client, _, mock_instrument_service = async_test_client
    mock_instrument_service.get_instruments.return_value = PaginatedInstrumentResponse(
        total=3,
        skip=0,
        limit=200,
        instruments=[
            {
                "security_id": "SEC_Z",
                "name": "Zulu Instrument",
                "isin": "US0000000001",
                "currency": "USD",
                "product_type": "Equity",
                "asset_class": "Equity",
            },
            {
                "security_id": "SEC_A",
                "name": "Alpha Instrument",
                "isin": "US0000000002",
                "currency": "USD",
                "product_type": "Equity",
                "asset_class": "Equity",
            },
            {
                "security_id": "BND_1",
                "name": "Bond One",
                "isin": "US0000000003",
                "currency": "USD",
                "product_type": "Bond",
                "asset_class": "Fixed Income",
            },
        ],
    )

    response = await client.get("/lookups/instruments?limit=200&product_type=Equity&q=alpha")
    assert response.status_code == 200
    items = response.json()["items"]
    _assert_lookup_items_contract(items)
    assert items == [{"id": "SEC_A", "label": "SEC_A | Alpha Instrument"}]


async def test_currency_lookup_contract_source_scope_and_uppercase(async_test_client):
    client, mock_portfolio_service, mock_instrument_service = async_test_client
    mock_portfolio_service.get_portfolios.return_value = PortfolioQueryResponse(portfolios=[])
    mock_instrument_service.get_instruments.side_effect = [
        PaginatedInstrumentResponse(
            total=51,
            skip=0,
            limit=50,
            instruments=[
                {
                    "security_id": "SEC_1",
                    "name": "Apple Inc.",
                    "isin": "US0378331005",
                    "currency": "usd",
                    "product_type": "Equity",
                    "asset_class": "Equity",
                }
            ],
        ),
        PaginatedInstrumentResponse(
            total=51,
            skip=50,
            limit=50,
            instruments=[
                {
                    "security_id": "SEC_2",
                    "name": "Siemens",
                    "isin": "DE0007236101",
                    "currency": "eur",
                    "product_type": "Equity",
                    "asset_class": "Equity",
                }
            ],
        ),
    ]

    response = await client.get("/lookups/currencies?source=INSTRUMENTS&q=US&limit=5")
    assert response.status_code == 200
    items = response.json()["items"]
    _assert_lookup_items_contract(items)
    assert items == [{"id": "USD", "label": "USD"}]
    mock_portfolio_service.get_portfolios.assert_not_called()
