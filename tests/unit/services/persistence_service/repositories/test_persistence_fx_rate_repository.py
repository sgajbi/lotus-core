from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from portfolio_common.events import FxRateEvent
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.persistence_service.app.repositories.fx_rate_repository import FxRateRepository


@pytest.mark.asyncio
async def test_upsert_fx_rate_uses_canonical_currency_codes() -> None:
    db = AsyncMock(spec=AsyncSession)
    repo = FxRateRepository(db)
    event = FxRateEvent(
        from_currency=" eur ",
        to_currency=" usd ",
        rate_date="2026-05-28",
        rate=Decimal("1.0875000000"),
    )

    persisted, status = await repo.upsert_fx_rate(event)

    assert status == "upserted"
    assert persisted.from_currency == "EUR"
    assert persisted.to_currency == "USD"
    db.execute.assert_awaited_once()
