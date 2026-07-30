from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.events import MarketPriceEvent
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.persistence_service.app.repositories.market_price_repository import (
    MarketPriceRepository,
)


@pytest.mark.asyncio
async def test_open_position_price_propagation_uses_nonzero_quantity() -> None:
    db = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db.execute.return_value = result
    repo = MarketPriceRepository(db)

    await repo.find_portfolios_with_open_position_before_date(
        "SEC_TEST_PRICE",
        date(2026, 5, 28),
    )

    statement = db.execute.await_args.args[0]
    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "anon_1.quantity != 0" in compiled
    assert "anon_1.quantity > 0" not in compiled


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
