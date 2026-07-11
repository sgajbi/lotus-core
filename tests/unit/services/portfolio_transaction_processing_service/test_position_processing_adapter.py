from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from portfolio_common.position_state_repository import PositionStateRepository
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    PositionProcessingCompatibilityAdapter,
    legacy_transaction_event_mapper,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.position_calculation_workflow import (  # noqa: E501
    PositionCalculationResult,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.position_repository import (  # noqa: E501
    PositionRepository,
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
        workflow=workflow,
    )

    result = await adapter.process(
        transaction,
        correlation_id="corr-001",
        traceparent="trace-001",
        rebuild_existing=True,
    )

    assert result.position_record_count == 2
    assert result.replay_queued is False
    assert result.cashflow_rebuild_transactions == (rebuilt_transaction,)
    event = workflow.calculate.await_args.kwargs["event"]
    assert event.transaction_id == "TX-001"
    assert event.correlation_id == "corr-001"
    assert event.traceparent == "trace-001"
    assert workflow.calculate.await_args.kwargs["rebuild_existing"] is True
    assert "outbox_repo" not in workflow.calculate.await_args.kwargs
