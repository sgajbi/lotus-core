from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.position_state_repository import PositionStateRepository
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.calculators.position_calculator.app.core.position_logic import (
    PositionCalculationResult,
)
from src.services.calculators.position_calculator.app.repositories.position_repository import (
    PositionRepository,
)
from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    PositionProcessingCompatibilityAdapter,
    legacy_transaction_event_mapper,
)


@pytest.mark.asyncio
async def test_position_adapter_returns_position_and_replay_outcome() -> None:
    transaction = BookedTransaction(
        transaction_id="TX-001",
        portfolio_id="PB-001",
        instrument_id="INST-001",
        security_id="SEC-001",
        transaction_date=datetime(2026, 4, 10, 9, 30, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("25.50"),
        gross_transaction_amount=Decimal("255.00"),
        trade_currency="SGD",
        currency="SGD",
    )
    workflow = AsyncMock()
    rebuilt_transaction = replace(transaction, transaction_id="TX-REBUILT", epoch=4)
    workflow.calculate.return_value = PositionCalculationResult(
        position_record_count=2,
        replay_queued=True,
        rebuilt_events=(
            legacy_transaction_event_mapper.to_transaction_event(
                rebuilt_transaction,
                correlation_id="corr-001",
                traceparent="trace-001",
            ),
        ),
    )
    adapter = PositionProcessingCompatibilityAdapter(
        db_session=AsyncMock(spec=AsyncSession),
        repository=AsyncMock(spec=PositionRepository),
        position_state_repository=AsyncMock(spec=PositionStateRepository),
        outbox_repository=AsyncMock(spec=OutboxRepository),
        workflow=workflow,
    )

    result = await adapter.process(
        transaction,
        correlation_id="corr-001",
        traceparent="trace-001",
    )

    assert result.position_record_count == 2
    assert result.replay_queued is True
    assert result.cashflow_rebuild_transactions == (rebuilt_transaction,)
    event = workflow.calculate.await_args.kwargs["event"]
    assert event.transaction_id == "TX-001"
    assert event.correlation_id == "corr-001"
    assert event.traceparent == "trace-001"
