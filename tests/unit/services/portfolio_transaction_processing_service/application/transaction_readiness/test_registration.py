"""Specify transaction-readiness registration and epoch-fencing behavior."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.services.portfolio_transaction_processing_service.app.application.transaction_readiness import (  # noqa: E501
    RegisterTransactionReadinessUseCase,
)
from src.services.portfolio_transaction_processing_service.app.domain import (
    BookedTransaction,
    TransactionStageRecord,
)


def _transaction(*, epoch: int = 4) -> BookedTransaction:
    return BookedTransaction(
        transaction_id="TX-READY-001",
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
        epoch=epoch,
    )


def _stage(*, status: str = "PENDING", cost_event_seen: bool = True) -> TransactionStageRecord:
    return TransactionStageRecord(
        stage_id=12,
        transaction_id="TX-READY-001",
        portfolio_id="PB-001",
        security_id="SEC-001",
        business_date=date(2026, 4, 10),
        epoch=4,
        status=status,
        cost_event_seen=cost_event_seen,
    )


@pytest.mark.asyncio
async def test_registers_current_epoch_and_stages_claimed_completion() -> None:
    repository = AsyncMock()
    repository.claim_processed_stage.return_value = _stage(status="COMPLETED")
    events = AsyncMock()
    use_case = RegisterTransactionReadinessUseCase(repository=repository, events=events)

    await use_case.register_processed_transactions(
        (_transaction(),),
        correlation_id="corr-001",
        traceparent="trace-001",
    )

    repository.acquire_stage_lock.assert_awaited_once_with(
        stage_name="TRANSACTION_PROCESSING",
        portfolio_id="PB-001",
        transaction_id="TX-READY-001",
    )
    repository.claim_processed_stage.assert_awaited_once_with(
        stage_name="TRANSACTION_PROCESSING",
        transaction_id="TX-READY-001",
        portfolio_id="PB-001",
        security_id="SEC-001",
        business_date=date(2026, 4, 10),
        epoch=4,
    )
    events.stage_transaction_readiness.assert_awaited_once_with(
        _stage(status="COMPLETED"),
        correlation_id="corr-001",
        traceparent="trace-001",
    )


@pytest.mark.asyncio
async def test_ignores_superseded_epoch_after_acquiring_exact_stage_lock() -> None:
    repository = AsyncMock()
    repository.claim_processed_stage.return_value = None
    events = AsyncMock()
    use_case = RegisterTransactionReadinessUseCase(repository=repository, events=events)

    await use_case.register_processed_transactions(
        (_transaction(epoch=4),), correlation_id=None, traceparent=None
    )

    repository.acquire_stage_lock.assert_awaited_once()
    repository.claim_processed_stage.assert_awaited_once_with(
        stage_name="TRANSACTION_PROCESSING",
        transaction_id="TX-READY-001",
        portfolio_id="PB-001",
        security_id="SEC-001",
        business_date=date(2026, 4, 10),
        epoch=4,
    )
    events.stage_transaction_readiness.assert_not_awaited()


@pytest.mark.asyncio
async def test_does_not_stage_an_unclaimed_completion() -> None:
    repository = AsyncMock()
    repository.claim_processed_stage.return_value = None
    events = AsyncMock()
    use_case = RegisterTransactionReadinessUseCase(repository=repository, events=events)

    await use_case.register_processed_transactions(
        (_transaction(),), correlation_id=None, traceparent=None
    )

    events.stage_transaction_readiness.assert_not_awaited()
