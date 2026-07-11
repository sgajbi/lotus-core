from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.query_control_plane_service.app.application.core_snapshot.errors import (
    CoreSnapshotUnavailableSectionError,
)
from src.services.query_control_plane_service.app.application.core_snapshot.market_data import (
    get_fx_rate_or_raise,
)

pytestmark = pytest.mark.asyncio


async def test_get_fx_rate_or_raise_returns_identity_rate_without_repository_lookup() -> None:
    fx_repo = AsyncMock()

    rate = await get_fx_rate_or_raise(
        source_reader=fx_repo,
        from_currency=" usd ",
        to_currency="USD",
        as_of_date=date(2026, 2, 27),
    )

    assert rate == Decimal("1")
    fx_repo.get_fx_rates.assert_not_awaited()


async def test_get_fx_rate_or_raise_rejects_blank_rate() -> None:
    fx_repo = AsyncMock()
    fx_repo.get_fx_rates.return_value = [SimpleNamespace(rate=" ")]

    with pytest.raises(CoreSnapshotUnavailableSectionError, match="missing FX rate EUR/USD"):
        await get_fx_rate_or_raise(
            source_reader=fx_repo,
            from_currency="EUR",
            to_currency="USD",
            as_of_date=date(2026, 2, 27),
        )
