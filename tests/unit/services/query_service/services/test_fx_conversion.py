import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
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


async def test_cached_fx_rate_converter_deduplicates_concurrent_lookup() -> None:
    lookup_started = asyncio.Event()
    second_lookup_started = asyncio.Event()
    release_lookup = asyncio.Event()
    repo_call_count = 0

    async def get_latest_fx_rate(**_: object) -> Decimal:
        nonlocal repo_call_count
        repo_call_count += 1
        lookup_started.set()
        await release_lookup.wait()
        return Decimal("1.25")

    repo = SimpleNamespace(get_latest_fx_rate=AsyncMock(side_effect=get_latest_fx_rate))
    converter = CachedFxRateConverter(repo)

    async def convert_second_amount() -> Decimal:
        second_lookup_started.set()
        return await converter.convert_amount(
            amount=Decimal("20"),
            from_currency="EUR",
            to_currency="USD",
            as_of_date=date(2026, 3, 27),
        )

    first_lookup = asyncio.create_task(
        converter.convert_amount(
            amount=Decimal("10"),
            from_currency=" eur ",
            to_currency=" usd ",
            as_of_date=date(2026, 3, 27),
        )
    )
    await lookup_started.wait()
    second_lookup = asyncio.create_task(convert_second_amount())
    await second_lookup_started.wait()
    await asyncio.sleep(0)

    assert repo_call_count == 1

    release_lookup.set()
    converted_amounts = await asyncio.gather(first_lookup, second_lookup)

    assert converted_amounts == [Decimal("12.50"), Decimal("25.00")]
    repo.get_latest_fx_rate.assert_awaited_once_with(
        from_currency="EUR",
        to_currency="USD",
        as_of_date=date(2026, 3, 27),
    )
    assert converter._inflight == {}


async def test_cached_fx_rate_converter_raises_for_missing_rate() -> None:
    repo = AsyncMock()
    repo.get_latest_fx_rate.return_value = None
    converter = CachedFxRateConverter(repo)

    with pytest.raises(ValueError, match="FX rate not found for CHF/USD as of 2026-03-27"):
        await converter.get_fx_rate(" chf ", " usd ", date(2026, 3, 27))
    with pytest.raises(ValueError, match="FX rate not found for CHF/USD as of 2026-03-27"):
        await converter.get_fx_rate("CHF", "USD", date(2026, 3, 27))
    assert repo.get_latest_fx_rate.await_count == 2


async def test_cached_fx_rate_converter_raises_for_blank_rate() -> None:
    repo = AsyncMock()
    repo.get_latest_fx_rate.return_value = " "
    converter = CachedFxRateConverter(repo)

    with pytest.raises(ValueError, match="FX rate not found for CHF/USD as of 2026-03-27"):
        await converter.get_fx_rate("CHF", "USD", date(2026, 3, 27))
