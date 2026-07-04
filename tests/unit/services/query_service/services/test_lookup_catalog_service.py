from unittest.mock import AsyncMock

import pytest

from src.services.query_service.app.dtos.lookup_dto import LookupItem
from src.services.query_service.app.services.lookup_catalog_service import LookupCatalogService

pytestmark = pytest.mark.asyncio


def _service() -> tuple[LookupCatalogService, AsyncMock, AsyncMock]:
    portfolio_service = AsyncMock()
    instrument_service = AsyncMock()
    return (
        LookupCatalogService(
            portfolio_service=portfolio_service,
            instrument_service=instrument_service,
        ),
        portfolio_service,
        instrument_service,
    )


async def test_lookup_catalog_delegates_portfolio_lookup_scope() -> None:
    service, portfolio_service, _ = _service()
    portfolio_service.search_portfolio_lookup_items.return_value = [
        LookupItem(id="PF_1", label="PF_1")
    ]

    result = await service.search_portfolio_lookup_items(
        client_id="CIF-1",
        booking_center_code="SGPB",
        q="PF",
        limit=5,
    )

    assert result == [LookupItem(id="PF_1", label="PF_1")]
    portfolio_service.search_portfolio_lookup_items.assert_awaited_once_with(
        client_id="CIF-1",
        booking_center_code="SGPB",
        q="PF",
        limit=5,
    )


async def test_lookup_catalog_delegates_instrument_lookup_scope() -> None:
    service, _, instrument_service = _service()
    instrument_service.search_instrument_lookup_items.return_value = [
        LookupItem(id="SEC_AAPL", label="Apple")
    ]

    result = await service.search_instrument_lookup_items(
        product_type="Equity",
        q="apple",
        limit=10,
    )

    assert result == [LookupItem(id="SEC_AAPL", label="Apple")]
    instrument_service.search_instrument_lookup_items.assert_awaited_once_with(
        product_type="Equity",
        q="apple",
        limit=10,
    )


async def test_lookup_catalog_merges_currency_sources_deterministically() -> None:
    service, portfolio_service, instrument_service = _service()
    portfolio_service.list_currency_lookup_items.return_value = [
        LookupItem(id="usd", label="USD"),
        {"id": "CHF", "label": "CHF"},
    ]
    instrument_service.list_currency_lookup_items.return_value = [
        LookupItem(id="eur", label="EUR"),
        LookupItem(id="USD", label="USD"),
    ]

    result = await service.list_currency_lookup_items(source="ALL", q=None, limit=3)

    assert result == [
        LookupItem(id="CHF", label="CHF"),
        LookupItem(id="EUR", label="EUR"),
        LookupItem(id="USD", label="USD"),
    ]
    portfolio_service.list_currency_lookup_items.assert_awaited_once_with(q=None, limit=3)
    instrument_service.list_currency_lookup_items.assert_awaited_once_with(q=None, limit=3)


async def test_lookup_catalog_honors_instrument_only_currency_scope() -> None:
    service, portfolio_service, instrument_service = _service()
    instrument_service.list_currency_lookup_items.return_value = [
        LookupItem(id="usd", label="USD"),
        LookupItem(id="eur", label="EUR"),
    ]

    result = await service.list_currency_lookup_items(source="INSTRUMENTS", q="u", limit=5)

    assert result == [
        LookupItem(id="EUR", label="EUR"),
        LookupItem(id="USD", label="USD"),
    ]
    portfolio_service.list_currency_lookup_items.assert_not_awaited()
    instrument_service.list_currency_lookup_items.assert_awaited_once_with(q="u", limit=5)


async def test_lookup_catalog_returns_empty_currency_catalog_for_empty_sources() -> None:
    service, portfolio_service, instrument_service = _service()
    portfolio_service.list_currency_lookup_items.return_value = []
    instrument_service.list_currency_lookup_items.return_value = []

    result = await service.list_currency_lookup_items(source="ALL", q="zzz", limit=5)

    assert result == []
