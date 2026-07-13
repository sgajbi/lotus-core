from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.outbox_repository import OutboxRepository
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.application import (
    TransactionProcessingError,
    TransactionProcessingRejected,
)
from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    SettlementCashRejectionReasonCode,
    SettlementCashValidationError,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    CashflowProcessingCompatibilityAdapter,
    CashflowProcessingOutcome,
    CashflowStageResult,
    LinkedCashLegError,
    NoCashflowRuleError,
    SqlAlchemyCashflowRepository,
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


def _adapter(stage_result: CashflowStageResult):
    workflow = AsyncMock()
    workflow.stage_valid_event.return_value = stage_result
    adapter = CashflowProcessingCompatibilityAdapter(
        workflow=workflow,
        db_session=AsyncMock(spec=AsyncSession),
        repository=AsyncMock(spec=SqlAlchemyCashflowRepository),
        idempotency_repository=AsyncMock(spec=IdempotencyRepository),
        outbox_repository=AsyncMock(spec=OutboxRepository),
    )
    return adapter, workflow


@pytest.mark.asyncio
async def test_cashflow_adapter_preserves_source_event_and_returns_record_count() -> None:
    adapter, workflow = _adapter(
        CashflowStageResult(
            outcome=CashflowProcessingOutcome.PROCESSED,
            cashflow_record_count=1,
        )
    )

    transaction = _transaction()
    result = await adapter.process(
        transaction,
        event_id="transactions.persisted-0-42",
        correlation_id="corr-001",
        traceparent="trace-001",
    )

    assert result.cashflow_record_count == 1
    stage_call = workflow.stage_valid_event.await_args.kwargs
    assert stage_call["event_id"] == "transactions.persisted-0-42"
    assert stage_call["event"].correlation_id == "corr-001"
    assert stage_call["event"].traceparent == "trace-001"
    assert stage_call["booked_transaction"] is transaction


@pytest.mark.asyncio
async def test_cashflow_adapter_rejects_stale_epoch_to_roll_back_combined_work() -> None:
    adapter, _workflow = _adapter(
        CashflowStageResult(outcome=CashflowProcessingOutcome.EPOCH_REJECTED)
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
        (NoCashflowRuleError("BUY rule missing"), "cashflow_rule_missing"),
        (LinkedCashLegError("linked cash leg missing"), "cashflow_contract_invalid"),
    ],
)
async def test_cashflow_adapter_maps_terminal_policy_errors(
    error: Exception,
    reason_code: str,
) -> None:
    adapter, workflow = _adapter(CashflowStageResult(outcome=CashflowProcessingOutcome.PROCESSED))
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


@pytest.mark.asyncio
async def test_cashflow_adapter_maps_settlement_rejection_for_dlq_delivery() -> None:
    adapter, workflow = _adapter(CashflowStageResult(outcome=CashflowProcessingOutcome.PROCESSED))
    workflow.stage_valid_event.side_effect = SettlementCashValidationError(
        reason_code=(SettlementCashRejectionReasonCode.DIVIDEND_NON_POSITIVE_NET_SETTLEMENT),
        field="trade_fee",
        message="DIVIDEND settlement cash must remain greater than zero after transaction fees.",
        available_proceeds=Decimal("10"),
        fee_amount=Decimal("11"),
        net_settlement_amount=Decimal("-1"),
    )

    with pytest.raises(TransactionProcessingRejected) as raised:
        await adapter.process(
            _transaction(),
            event_id="transactions.persisted-0-42",
            correlation_id="corr-001",
            traceparent=None,
        )

    assert raised.value.reason_code == "DIVIDEND_013_NON_POSITIVE_NET_SETTLEMENT"
    assert raised.value.retryable is False
    assert raised.value.detail["net_settlement_amount"] == "-1"
