from __future__ import annotations

from datetime import UTC, date, datetime
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

    assert rate.value == Decimal("1")
    assert rate.effective_as_of_date is None
    assert rate.observation() is None
    fx_repo.get_fx_rates.assert_not_awaited()


async def test_get_fx_rate_or_raise_rejects_blank_rate() -> None:
    fx_repo = AsyncMock()
    fx_repo.get_fx_rates.return_value = [SimpleNamespace(rate=" ", rate_date=date(2026, 2, 27))]

    with pytest.raises(CoreSnapshotUnavailableSectionError, match="missing FX rate EUR/USD"):
        await get_fx_rate_or_raise(
            source_reader=fx_repo,
            from_currency="EUR",
            to_currency="USD",
            as_of_date=date(2026, 2, 27),
        )


async def test_get_fx_rate_or_raise_preserves_observation_timestamp() -> None:
    evidence_timestamp = datetime(2026, 2, 27, 11, tzinfo=UTC)
    fx_repo = AsyncMock()
    fx_repo.get_fx_rates.return_value = [
        SimpleNamespace(
            rate=Decimal("1.25"),
            rate_date=date(2026, 2, 27),
            evidence_timestamp=evidence_timestamp,
        )
    ]

    rate = await get_fx_rate_or_raise(
        source_reader=fx_repo,
        from_currency="EUR",
        to_currency="USD",
        as_of_date=date(2026, 2, 27),
    )

    assert rate.evidence_timestamp == evidence_timestamp
    assert rate.observation() is not None
    assert rate.observation().evidence_timestamp == evidence_timestamp
