"""Unit tests for transaction-owned pipeline stage readiness."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from portfolio_common.config import (
    KAFKA_PORTFOLIO_SECURITY_DAY_VALUATION_READY_TOPIC,
    KAFKA_TRANSACTION_PROCESSING_READY_TOPIC,
)

from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    PipelineStageProcessingAdapter,
)


def _transaction(*, epoch: int = 4, security_id: str = "SEC-001") -> BookedTransaction:
    return BookedTransaction(
        transaction_id="TX-PIPE-001",
        portfolio_id="PB-001",
        instrument_id="INST-001",
        security_id=security_id,
        transaction_date=datetime(2026, 4, 10, 9, 30, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("25.50"),
        gross_transaction_amount=Decimal("255.00"),
        trade_currency="SGD",
        currency="SGD",
        epoch=epoch,
    )


def _stage(*, security_id: str | None = "SEC-001", status: str = "PENDING") -> SimpleNamespace:
    return SimpleNamespace(
        id=12,
        transaction_id="TX-PIPE-001",
        portfolio_id="PB-001",
        security_id=security_id,
        business_date=date(2026, 4, 10),
        epoch=4,
        status=status,
        cost_event_seen=True,
    )


@pytest.mark.asyncio
async def test_register_processed_transaction_claims_stage_and_emits_governed_events() -> None:
    repository = AsyncMock()
    repository.latest_epoch.return_value = 3
    repository.upsert_processed_stage.return_value = _stage()
    repository.claim_completion.return_value = True
    outbox_repository = AsyncMock()
    adapter = PipelineStageProcessingAdapter(repository, outbox_repository)

    await adapter.register_processed_transactions(
        (_transaction(),),
        correlation_id="corr-001",
        traceparent="trace-001",
    )

    repository.acquire_stage_lock.assert_awaited_once_with(
        stage_name="TRANSACTION_PROCESSING",
        portfolio_id="PB-001",
        transaction_id="TX-PIPE-001",
    )
    repository.upsert_processed_stage.assert_awaited_once_with(
        stage_name="TRANSACTION_PROCESSING",
        transaction_id="TX-PIPE-001",
        portfolio_id="PB-001",
        security_id="SEC-001",
        business_date=date(2026, 4, 10),
        epoch=4,
    )
    assert outbox_repository.create_outbox_event.await_count == 2
    completed_call, valuation_call = outbox_repository.create_outbox_event.await_args_list
    assert completed_call.kwargs["aggregate_id"] == "PB-001:TX-PIPE-001:4"
    assert completed_call.kwargs["event_type"] == "TransactionProcessingCompleted"
    assert completed_call.kwargs["topic"] == KAFKA_TRANSACTION_PROCESSING_READY_TOPIC
    assert completed_call.kwargs["payload"]["readiness_reason"] == (
        "atomic_transaction_processing_completed"
    )
    assert valuation_call.kwargs["aggregate_id"] == "PB-001:SEC-001:2026-04-10:4"
    assert valuation_call.kwargs["event_type"] == "PortfolioDayReadyForValuation"
    assert valuation_call.kwargs["topic"] == KAFKA_PORTFOLIO_SECURITY_DAY_VALUATION_READY_TOPIC


@pytest.mark.asyncio
async def test_superseded_epoch_is_locked_then_ignored_without_persistence_or_events() -> None:
    repository = AsyncMock()
    repository.latest_epoch.return_value = 5
    outbox_repository = AsyncMock()
    adapter = PipelineStageProcessingAdapter(repository, outbox_repository)

    await adapter.register_processed_transactions(
        (_transaction(epoch=4),),
        correlation_id="corr-001",
        traceparent=None,
    )

    repository.acquire_stage_lock.assert_awaited_once()
    repository.upsert_processed_stage.assert_not_awaited()
    repository.claim_completion.assert_not_awaited()
    outbox_repository.create_outbox_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_unclaimed_stage_does_not_emit_duplicate_events() -> None:
    repository = AsyncMock()
    repository.latest_epoch.return_value = 4
    repository.upsert_processed_stage.return_value = _stage()
    repository.claim_completion.return_value = False
    outbox_repository = AsyncMock()
    adapter = PipelineStageProcessingAdapter(repository, outbox_repository)

    await adapter.register_processed_transactions(
        (_transaction(),),
        correlation_id=None,
        traceparent=None,
    )

    outbox_repository.create_outbox_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_stage_without_security_emits_completion_without_valuation_readiness() -> None:
    repository = AsyncMock()
    repository.latest_epoch.return_value = None
    repository.upsert_processed_stage.return_value = _stage(security_id=None)
    repository.claim_completion.return_value = True
    outbox_repository = AsyncMock()
    adapter = PipelineStageProcessingAdapter(repository, outbox_repository)

    await adapter.register_processed_transactions(
        (_transaction(security_id=""),),
        correlation_id="corr-001",
        traceparent=None,
    )

    outbox_repository.create_outbox_event.assert_awaited_once()
    assert outbox_repository.create_outbox_event.await_args.kwargs["event_type"] == (
        "TransactionProcessingCompleted"
    )
