from __future__ import annotations

from dataclasses import fields
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import Portfolio
from portfolio_common.events import TransactionEvent
from portfolio_common.outbox_repository import OutboxRepository

from src.services.portfolio_transaction_processing_service.app.application import (
    TransactionProcessingError,
)
from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    CostCalculatorRepository,
    CostProcessingCompatibilityAdapter,
)


@pytest.mark.asyncio
async def test_cost_adapter_maps_domain_and_returns_every_processed_leg() -> None:
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
    processed_event = TransactionEvent.model_validate(
        {
            **{field.name: getattr(transaction, field.name) for field in fields(transaction)},
            "transaction_id": "TX-001-COSTED",
            "correlation_id": "corr-001",
            "traceparent": "trace-001",
        }
    )
    instrument_event = MagicMock()
    repository = AsyncMock(spec=CostCalculatorRepository)
    repository.get_portfolio.return_value = Portfolio(
        base_currency="SGD",
        portfolio_id="PB-001",
    )
    repository.get_instrument.return_value = MagicMock()
    outbox_repository = AsyncMock(spec=OutboxRepository)
    workflow = MagicMock()
    workflow._prepare_transaction_event = AsyncMock(return_value=(processed_event, "BUY", "FIFO"))
    workflow._assert_required_instrument_reference_available = MagicMock()
    workflow._build_events_to_publish = AsyncMock(
        return_value=([processed_event], [instrument_event])
    )
    workflow._build_emitted_transaction_events = AsyncMock(return_value=[processed_event])
    workflow._publish_transaction_events = AsyncMock()
    workflow._publish_instrument_events = AsyncMock()
    adapter = CostProcessingCompatibilityAdapter(
        workflow=workflow,
        repository=repository,
        outbox_repository=outbox_repository,
    )

    result = await adapter.process(
        transaction,
        correlation_id="corr-001",
        traceparent="trace-001",
    )

    assert [item.transaction_id for item in result.processed_transactions] == ["TX-001-COSTED"]
    assert result.instrument_update_count == 1
    input_event = workflow._prepare_transaction_event.await_args.args[0]
    assert input_event.transaction_id == "TX-001"
    assert input_event.correlation_id == "corr-001"
    assert input_event.traceparent == "trace-001"


@pytest.mark.asyncio
async def test_cost_adapter_maps_missing_reference_data_to_retryable_application_error() -> None:
    transaction = BookedTransaction(
        transaction_id="TX-MISSING-PORTFOLIO",
        portfolio_id="PB-MISSING",
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
    repository = AsyncMock(spec=CostCalculatorRepository)
    repository.get_portfolio.return_value = None
    adapter = CostProcessingCompatibilityAdapter(
        workflow=MagicMock(),
        repository=repository,
        outbox_repository=AsyncMock(spec=OutboxRepository),
    )

    with pytest.raises(TransactionProcessingError) as exc_info:
        await adapter.process(transaction, correlation_id="corr-001", traceparent=None)

    assert exc_info.value.reason_code == "cost_dependency_unavailable"
    assert exc_info.value.retryable is True
