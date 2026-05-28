from unittest.mock import AsyncMock

import pytest
from portfolio_common.events import InstrumentEvent
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.persistence_service.app.repositories.instrument_repository import (
    InstrumentRepository,
)


@pytest.mark.asyncio
async def test_create_or_update_instrument_uses_canonical_currency_codes() -> None:
    db = AsyncMock(spec=AsyncSession)
    repo = InstrumentRepository(db)
    event = InstrumentEvent(
        security_id="FX_FORWARD_001",
        name="EUR/USD Forward",
        isin="FXFORWARD001",
        currency=" usd ",
        product_type="fx_forward",
        pair_base_currency=" eur ",
        pair_quote_currency=" usd ",
        buy_currency=" eur ",
        sell_currency=" usd ",
    )

    persisted = await repo.create_or_update_instrument(event)

    assert persisted.currency == "USD"
    assert persisted.pair_base_currency == "EUR"
    assert persisted.pair_quote_currency == "USD"
    assert persisted.buy_currency == "EUR"
    assert persisted.sell_currency == "USD"
    db.execute.assert_awaited_once()
