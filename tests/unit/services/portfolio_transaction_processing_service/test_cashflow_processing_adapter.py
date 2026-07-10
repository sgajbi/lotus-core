from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.outbox_repository import OutboxRepository
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.calculators.cashflow_calculator_service.app.consumers import (
    transaction_consumer as cashflow,
)
from src.services.calculators.cashflow_calculator_service.app.repositories import (
    cashflow_repository,
)
from src.services.portfolio_transaction_processing_service.app.application import (
    TransactionProcessingError,
    TransactionProcessingRejected,
)
from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    CashflowProcessingCompatibilityAdapter,
)


def _transaction() -> BookedTransaction:
    return BookedTransaction(
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


def _adapter(stage_result: cashflow.CashflowStageResult):
    workflow = AsyncMock()
    workflow.stage_valid_event.return_value = stage_result
    adapter = CashflowProcessingCompatibilityAdapter(
        workflow=workflow,
        db_session=AsyncMock(spec=AsyncSession),
        repository=AsyncMock(spec=cashflow_repository.CashflowRepository),
        idempotency_repository=AsyncMock(spec=IdempotencyRepository),
        outbox_repository=AsyncMock(spec=OutboxRepository),
    )
    return adapter, workflow


@pytest.mark.asyncio
async def test_cashflow_adapter_preserves_source_event_and_returns_record_count() -> None:
    adapter, workflow = _adapter(
        cashflow.CashflowStageResult(
            outcome=cashflow.CashflowProcessingOutcome.PROCESSED,
            cashflow_record_count=1,
        )
    )

    result = await adapter.process(
        _transaction(),
        event_id="transactions.persisted-0-42",
        correlation_id="corr-001",
        traceparent="trace-001",
    )

    assert result.cashflow_record_count == 1
    stage_call = workflow.stage_valid_event.await_args.kwargs
    assert stage_call["event_id"] == "transactions.persisted-0-42"
    assert stage_call["event"].correlation_id == "corr-001"
    assert stage_call["event"].traceparent == "trace-001"


@pytest.mark.asyncio
async def test_cashflow_adapter_rejects_stale_epoch_to_roll_back_combined_work() -> None:
    adapter, _workflow = _adapter(
        cashflow.CashflowStageResult(outcome=cashflow.CashflowProcessingOutcome.EPOCH_REJECTED)
    )

    with pytest.raises(TransactionProcessingRejected) as exc_info:
        await adapter.process(
            _transaction(),
            event_id="transactions.persisted-0-42",
            correlation_id="corr-001",
            traceparent=None,
        )

    assert exc_info.value.reason_code == "cashflow_epoch_rejected"
    assert exc_info.value.retryable is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "reason_code"),
    [
        (cashflow.NoCashflowRuleError("BUY rule missing"), "cashflow_rule_missing"),
        (cashflow.LinkedCashLegError("linked cash leg missing"), "cashflow_contract_invalid"),
    ],
)
async def test_cashflow_adapter_maps_terminal_policy_errors(
    error: Exception,
    reason_code: str,
) -> None:
    adapter, workflow = _adapter(
        cashflow.CashflowStageResult(outcome=cashflow.CashflowProcessingOutcome.PROCESSED)
    )
    workflow.stage_valid_event.side_effect = error

    with pytest.raises(TransactionProcessingError) as exc_info:
        await adapter.process(
            _transaction(),
            event_id="transactions.persisted-0-42",
            correlation_id="corr-001",
            traceparent=None,
        )

    assert exc_info.value.reason_code == reason_code
    assert exc_info.value.retryable is False
