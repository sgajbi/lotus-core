"""SQL adapter tests for dated market FX evidence."""

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.query_control_plane_service.app.infrastructure.market_fx_sources import (
    SqlAlchemyMarketFxRateReader,
)


@pytest.mark.asyncio
async def test_fx_query_normalizes_pair_and_returns_typed_ordered_evidence() -> None:
    timestamp = datetime(2026, 4, 10, 10, tzinfo=UTC)
    row = SimpleNamespace(
        from_currency=" usd ",
        to_currency="sgd",
        rate_date=date(2026, 4, 10),
        rate=Decimal("1.3456"),
        created_at=timestamp,
        updated_at=timestamp,
    )
    result = MagicMock()
    result.scalars.return_value.all.return_value = [row]
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)

    records = await SqlAlchemyMarketFxRateReader(session).list_rates(
        from_currency=" usd ",
        to_currency=" sgd ",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 10),
    )

    assert records[0].from_currency == "USD"
    assert records[0].to_currency == "SGD"
    assert records[0].rate == Decimal("1.3456")
    sql = str(session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "upper(trim(fx_rates.from_currency)) = 'USD'" in sql
    assert "upper(trim(fx_rates.to_currency)) = 'SGD'" in sql
    assert "ORDER BY fx_rates.rate_date ASC" in sql
