"""Unit tests for the combined-runtime pipeline stage adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.services.pipeline_orchestrator_service.app.services.pipeline_orchestrator_service import (
    PipelineOrchestratorService,
)
from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    PipelineStageProcessingCompatibilityAdapter,
)


def _transaction() -> BookedTransaction:
    return BookedTransaction(
        transaction_id="TX-PIPE-001",
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
        epoch=4,
    )


@pytest.mark.asyncio
async def test_pipeline_stage_adapter_registers_processed_transactions_with_event_metadata() -> (
    None
):
    service = AsyncMock(spec=PipelineOrchestratorService)
    adapter = PipelineStageProcessingCompatibilityAdapter(service)

    await adapter.register_processed_transactions(
        (_transaction(),),
        correlation_id="corr-001",
        traceparent="trace-001",
    )

    service.register_processed_transaction.assert_awaited_once()
    event, correlation_id = service.register_processed_transaction.await_args.args
    assert event.transaction_id == "TX-PIPE-001"
    assert event.portfolio_id == "PB-001"
    assert event.security_id == "SEC-001"
    assert event.epoch == 4
    assert event.correlation_id == "corr-001"
    assert event.traceparent == "trace-001"
    assert correlation_id == "corr-001"
