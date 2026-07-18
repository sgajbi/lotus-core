"""Test the SQLAlchemy position recalculation state adapter."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from portfolio_common.position_state_repository import PositionStateRepository

from src.services.portfolio_transaction_processing_service.app.infrastructure.position.recalculation_state import (  # noqa: E501
    SqlAlchemyPositionRecalculationStateStore,
)


@pytest.mark.asyncio
async def test_state_store_maps_shared_repository_state_to_domain_record() -> None:
    repository = AsyncMock(spec=PositionStateRepository)
    repository.get_or_create_state.return_value = SimpleNamespace(
        portfolio_id="PB-001",
        security_id="SEC-001",
        epoch=3,
        watermark_date=date(2026, 4, 9),
        status="CURRENT",
    )
    store = SqlAlchemyPositionRecalculationStateStore(repository)

    state = await store.get_or_create(portfolio_id="PB-001", security_id="SEC-001")

    assert state.portfolio_id == "PB-001"
    assert state.security_id == "SEC-001"
    assert state.epoch == 3
    assert state.watermark_date == date(2026, 4, 9)
    assert state.status == "CURRENT"


@pytest.mark.asyncio
async def test_state_store_preserves_stale_epoch_compare_and_set_outcome() -> None:
    repository = AsyncMock(spec=PositionStateRepository)
    repository.increment_epoch_and_reset_watermark.return_value = None
    store = SqlAlchemyPositionRecalculationStateStore(repository)

    state = await store.advance_epoch(
        portfolio_id="PB-001",
        security_id="SEC-001",
        expected_epoch=3,
        watermark_date=date(2026, 4, 9),
    )

    assert state is None
    repository.increment_epoch_and_reset_watermark.assert_awaited_once_with(
        "PB-001",
        "SEC-001",
        3,
        date(2026, 4, 9),
    )


@pytest.mark.asyncio
async def test_state_store_rearms_generation_only_for_expected_epoch_without_committing() -> None:
    repository = AsyncMock(spec=PositionStateRepository)
    repository.update_watermarks_if_older.return_value = 1
    store = SqlAlchemyPositionRecalculationStateStore(repository)

    updated = await store.rearm_generation(
        portfolio_id="PB-001",
        security_id="SEC-001",
        expected_epoch=3,
        watermark_date=date(2026, 4, 9),
    )

    assert updated is True
    repository.update_watermarks_if_older.assert_awaited_once_with(
        keys=[("PB-001", "SEC-001")],
        new_watermark_date=date(2026, 4, 9),
        touch_if_already_lagging=True,
        expected_epoch=3,
    )
