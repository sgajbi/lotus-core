from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.services.query_service.app.services.fx_conversion import CachedFxRateConverter

pytestmark = pytest.mark.asyncio


async def test_cached_fx_rate_converter_returns_identity_amount_without_repository_call() -> None:
    repo = AsyncMock()
    converter = CachedFxRateConverter(repo)

    amount = await converter.convert_amount(
        amount=Decimal("10"),
        from_currency=" usd ",
        to_currency="USD",
        as_of_date=date(2026, 3, 27),
    )

    assert amount == Decimal("10")
    repo.get_latest_fx_rate.assert_not_awaited()


async def test_cached_fx_rate_converter_normalizes_and_caches_rate_lookup() -> None:
    repo = AsyncMock()
    repo.get_latest_fx_rate.return_value = Decimal("1.25")
    converter = CachedFxRateConverter(repo)

    first = await converter.get_fx_rate(" eur ", " usd ", date(2026, 3, 27))
    second = await converter.get_fx_rate("EUR", "USD", date(2026, 3, 27))

    assert first == Decimal("1.25")
    assert second == Decimal("1.25")
    repo.get_latest_fx_rate.assert_awaited_once_with(
        from_currency="EUR",
        to_currency="USD",
        as_of_date=date(2026, 3, 27),
    )


async def test_cached_fx_rate_converter_raises_for_missing_rate() -> None:
    repo = AsyncMock()
    repo.get_latest_fx_rate.return_value = None
    converter = CachedFxRateConverter(repo)

    with pytest.raises(ValueError, match="FX rate not found for CHF/USD as of 2026-03-27"):
        await converter.get_fx_rate(" chf ", " usd ", date(2026, 3, 27))
