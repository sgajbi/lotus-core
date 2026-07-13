"""Test position recalculation state and epoch-fence adapters."""

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from portfolio_common.position_state_repository import PositionStateRepository
from portfolio_common.reprocessing import EpochFencer

from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.infrastructure.position_epoch_fence_adapter import (  # noqa: E501
    PositionEpochFenceAdapter,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.sqlalchemy_position_recalculation_state_store import (  # noqa: E501
    SqlAlchemyPositionRecalculationStateStore,
)


def _transaction(*, epoch: int | None = 3) -> BookedTransaction:
    return BookedTransaction(
        transaction_id="TX-001",
        portfolio_id="PB-001",
        instrument_id="SEC-001",
        security_id="SEC-001",
        transaction_date=datetime(2026, 4, 10, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("10"),
        gross_transaction_amount=Decimal("100"),
        trade_currency="SGD",
        currency="SGD",
        epoch=epoch,
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
async def test_state_store_rearms_generation_without_committing() -> None:
    repository = AsyncMock(spec=PositionStateRepository)
    repository.update_watermarks_if_older.return_value = 1
    store = SqlAlchemyPositionRecalculationStateStore(repository)

    updated = await store.rearm_generation(
        portfolio_id="PB-001",
        security_id="SEC-001",
        watermark_date=date(2026, 4, 9),
    )

    assert updated is True
    repository.update_watermarks_if_older.assert_awaited_once_with(
        keys=[("PB-001", "SEC-001")],
        new_watermark_date=date(2026, 4, 9),
        touch_if_already_lagging=True,
    )


@pytest.mark.asyncio
async def test_epoch_fence_adapter_uses_minimal_domain_envelope() -> None:
    fencer = AsyncMock(spec=EpochFencer)
    fencer.check.return_value = True
    adapter = PositionEpochFenceAdapter(fencer)
    transaction = _transaction(epoch=3)

    assert await adapter.is_current(transaction) is True

    envelope = fencer.check.await_args.args[0]
    assert envelope.portfolio_id == "PB-001"
    assert envelope.security_id == "SEC-001"
    assert envelope.epoch == 3
    assert envelope.topic is None
    assert not hasattr(envelope, "transaction_type")
