from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from portfolio_common.events import MarketPriceEvent
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.persistence_service.app.repositories.market_price_repository import (
    MarketPriceRepository,
)


@pytest.mark.asyncio
async def test_create_market_price_uses_canonical_currency_code() -> None:
    db = AsyncMock(spec=AsyncSession)
    repo = MarketPriceRepository(db)
    event = MarketPriceEvent(
        security_id="SEC_TEST_PRICE",
        price_date="2026-05-28",
        price=Decimal("101.2500000000"),
        currency=" usd ",
    )

    persisted = await repo.create_market_price(event)

    assert persisted.currency == "USD"
    db.execute.assert_awaited_once()
