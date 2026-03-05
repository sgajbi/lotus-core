from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from portfolio_common.db import get_async_db_session
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.dtos.fx_rate_dto import FxRateResponse
from src.services.query_service.app.dtos.instrument_dto import PaginatedInstrumentResponse
from src.services.query_service.app.dtos.portfolio_dto import PortfolioQueryResponse
from src.services.query_service.app.dtos.price_dto import MarketPriceResponse
from src.services.query_service.app.main import app

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client():
    mock_fx_service = MagicMock()
    mock_fx_service.get_fx_rates = AsyncMock(
        return_value=FxRateResponse(from_currency="USD", to_currency="SGD", rates=[])
    )
    mock_instrument_service = MagicMock()
    mock_instrument_service.get_instruments = AsyncMock(
        return_value=PaginatedInstrumentResponse(total=0, skip=0, limit=50, instruments=[])
    )
    mock_price_service = MagicMock()
    mock_price_service.get_prices = AsyncMock(
        return_value=MarketPriceResponse(security_id="SEC_1", prices=[])
    )
    mock_portfolio_service = MagicMock()
    mock_portfolio_service.get_portfolios = AsyncMock(
        return_value=PortfolioQueryResponse(portfolios=[])
    )

    app.dependency_overrides[get_async_db_session] = lambda: AsyncMock(spec=AsyncSession)

    with (
        patch(
            "src.services.query_service.app.routers.fx_rates.FxRateService",
            return_value=mock_fx_service,
        ),
        patch(
            "src.services.query_service.app.routers.instruments.InstrumentService",
            return_value=mock_instrument_service,
        ),
        patch(
            "src.services.query_service.app.routers.prices.MarketPriceService",
            return_value=mock_price_service,
        ),
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
            yield (
                client,
                mock_fx_service,
                mock_instrument_service,
                mock_price_service,
                mock_portfolio_service,
            )

    app.dependency_overrides.pop(get_async_db_session, None)


async def test_get_fx_rates_success_and_uppercase(async_test_client):
    client, mock_fx_service, _, _, _ = async_test_client

    response = await client.get(
        "/fx-rates/",
        params={
            "from_currency": "usd",
            "to_currency": "sgd",
            "start_date": "2025-01-01",
            "end_date": "2025-01-31",
        },
    )

    assert response.status_code == 200
    assert response.json()["from_currency"] == "USD"
    assert response.json()["to_currency"] == "SGD"
    mock_fx_service.get_fx_rates.assert_awaited_once_with(
        from_currency="USD",
        to_currency="SGD",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
    )


async def test_get_instruments_success_with_pagination(async_test_client):
    client, _, mock_instrument_service, _, _ = async_test_client

    response = await client.get(
        "/instruments/",
        params={"security_id": "SEC_1", "product_type": "Equity", "skip": 10, "limit": 25},
    )

    assert response.status_code == 200
    mock_instrument_service.get_instruments.assert_awaited_once_with(
        security_id="SEC_1",
        product_type="Equity",
        skip=10,
        limit=25,
    )


async def test_get_prices_success(async_test_client):
    client, _, _, mock_price_service, _ = async_test_client

    response = await client.get(
        "/prices/",
        params={
            "security_id": "SEC_1",
            "start_date": "2025-01-01",
            "end_date": "2025-01-31",
        },
    )

    assert response.status_code == 200
    assert response.json()["security_id"] == "SEC_1"
    mock_price_service.get_prices.assert_awaited_once_with(
        security_id="SEC_1",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
    )


async def test_get_portfolio_lookups(async_test_client):
    client, _, _, _, mock_portfolio_service = async_test_client
    mock_portfolio_service.get_portfolios.return_value = PortfolioQueryResponse(
        portfolios=[
            {
                "portfolio_id": "PF_1",
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
            }
        ]
    )

    response = await client.get("/lookups/portfolios")
    assert response.status_code == 200
    assert response.json()["items"] == [{"id": "PF_1", "label": "PF_1"}]


async def test_get_portfolio_lookups_filters_query_and_limit(async_test_client):
    client, _, _, _, mock_portfolio_service = async_test_client
    mock_portfolio_service.get_portfolios.return_value = PortfolioQueryResponse(
        portfolios=[
            {
                "portfolio_id": "PF_9",
                "base_currency": "USD",
                "open_date": "2025-01-01",
                "close_date": None,
                "risk_exposure": "MODERATE",
                "investment_time_horizon": "LONG_TERM",
                "portfolio_type": "DISCRETIONARY",
                "objective": "GROWTH",
                "booking_center_code": "LON-01",
                "client_id": "CIF-9",
                "is_leverage_allowed": False,
                "advisor_id": "ADV-9",
                "status": "ACTIVE",
            },
            {
                "portfolio_id": "PF_1",
                "base_currency": "USD",
                "open_date": "2025-01-01",
                "close_date": None,
                "risk_exposure": "MODERATE",
                "investment_time_horizon": "LONG_TERM",
                "portfolio_type": "DISCRETIONARY",
                "objective": "GROWTH",
                "booking_center_code": "LON-01",
                "client_id": "CIF-9",
                "is_leverage_allowed": False,
                "advisor_id": "ADV-9",
                "status": "ACTIVE",
            },
        ]
    )

    response = await client.get("/lookups/portfolios?client_id=CIF-9&q=PF_&limit=1")
    assert response.status_code == 200
    assert response.json()["items"] == [{"id": "PF_1", "label": "PF_1"}]
    mock_portfolio_service.get_portfolios.assert_awaited_once_with(
        client_id="CIF-9",
        booking_center_code=None,
    )


async def test_get_instrument_lookups(async_test_client):
    client, _, mock_instrument_service, _, _ = async_test_client
    mock_instrument_service.get_instruments.return_value = PaginatedInstrumentResponse(
        total=1,
        skip=0,
        limit=200,
        instruments=[
            {
                "security_id": "SEC_1",
                "name": "Apple Inc.",
                "isin": "US0378331005",
                "currency": "USD",
                "product_type": "Equity",
                "asset_class": "Equity",
            }
        ],
    )

    response = await client.get("/lookups/instruments?limit=200")
    assert response.status_code == 200
    assert response.json()["items"] == [{"id": "SEC_1", "label": "SEC_1 | Apple Inc."}]


async def test_get_instrument_lookups_with_product_type_and_query(async_test_client):
    client, _, mock_instrument_service, _, _ = async_test_client
    mock_instrument_service.get_instruments.return_value = PaginatedInstrumentResponse(
        total=2,
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
        ],
    )

    response = await client.get("/lookups/instruments?limit=200&product_type=Equity&q=alpha")
    assert response.status_code == 200
    assert response.json()["items"] == [{"id": "SEC_A", "label": "SEC_A | Alpha Instrument"}]
    mock_instrument_service.get_instruments.assert_awaited_once_with(
        skip=0,
        limit=200,
        product_type="Equity",
    )


async def test_get_currency_lookups(async_test_client):
    client, _, mock_instrument_service, _, mock_portfolio_service = async_test_client
    mock_portfolio_service.get_portfolios.return_value = PortfolioQueryResponse(
        portfolios=[
            {
                "portfolio_id": "PF_1",
                "base_currency": "usd",
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
            }
        ]
    )
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
                    "currency": "eur",
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
                    "name": "Tesla Inc.",
                    "isin": "US88160R1014",
                    "currency": "USD",
                    "product_type": "Equity",
                    "asset_class": "Equity",
                }
            ],
        ),
    ]

    response = await client.get("/lookups/currencies?instrument_page_limit=50")
    assert response.status_code == 200
    assert response.json()["items"] == [
        {"id": "EUR", "label": "EUR"},
        {"id": "USD", "label": "USD"},
    ]


async def test_get_currency_lookups_source_and_query(async_test_client):
    client, _, mock_instrument_service, _, mock_portfolio_service = async_test_client
    mock_portfolio_service.get_portfolios.return_value = PortfolioQueryResponse(
        portfolios=[
            {
                "portfolio_id": "PF_1",
                "base_currency": "gbp",
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
            }
        ]
    )
    mock_instrument_service.get_instruments.return_value = PaginatedInstrumentResponse(
        total=1,
        skip=0,
        limit=500,
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
    )

    response = await client.get("/lookups/currencies?source=INSTRUMENTS&q=US&limit=1")
    assert response.status_code == 200
    assert response.json()["items"] == [{"id": "USD", "label": "USD"}]
    mock_portfolio_service.get_portfolios.assert_not_called()
