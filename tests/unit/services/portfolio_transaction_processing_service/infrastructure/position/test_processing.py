from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.services.portfolio_transaction_processing_service.app.application.position_history import (
    PositionHistoryProcessingResult,
    PositionHistoryProcessor,
)
from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.infrastructure.position import (
    PositionHistoryProcessingAdapter,
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
    processor = AsyncMock(spec=PositionHistoryProcessor)
    rebuilt_transaction = replace(transaction, transaction_id="TX-REBUILT", epoch=4)
    processor.process.return_value = PositionHistoryProcessingResult(
        position_record_count=2,
        rebuilt_transactions=(rebuilt_transaction,),
    )
    adapter = PositionHistoryProcessingAdapter(processor=processor)

    result = await adapter.process(
        transaction,
        correlation_id="corr-001",
        traceparent="trace-001",
        rebuild_existing=True,
    )

    assert result.position_record_count == 2
    assert result.replay_queued is False
    assert result.cashflow_rebuild_transactions == (rebuilt_transaction,)
    processor.process.assert_awaited_once_with(transaction, rebuild_existing=True)
