"""Verify governed transaction and valuation readiness outbox mappings."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest
from portfolio_common.config import (
    KAFKA_PORTFOLIO_SECURITY_DAY_VALUATION_READY_TOPIC,
    KAFKA_TRANSACTION_PROCESSING_READY_TOPIC,
)

from src.services.portfolio_transaction_processing_service.app.domain import TransactionStageRecord
from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_readiness import (  # noqa: E501
    TransactionalTransactionReadinessEventStager,
)


def _stage(*, security_id: str | None = "SEC-001") -> TransactionStageRecord:
    return TransactionStageRecord(
        stage_id=12,
        transaction_id="TX-READY-001",
        portfolio_id="PB-001",
        security_id=security_id,
        business_date=date(2026, 4, 10),
        epoch=4,
        status="PENDING",
        cost_event_seen=True,
    )


@pytest.mark.asyncio
async def test_stages_transaction_and_valuation_readiness_events() -> None:
    outbox_repository = AsyncMock()
    stager = TransactionalTransactionReadinessEventStager(outbox_repository)

    await stager.stage_transaction_readiness(
        _stage(),
        correlation_id="corr-001",
        traceparent="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
    )

    assert outbox_repository.create_outbox_event.await_count == 2
    completed_call, valuation_call = outbox_repository.create_outbox_event.await_args_list
    assert completed_call.kwargs["aggregate_id"] == "PB-001:TX-READY-001:4"
    assert completed_call.kwargs["event_type"] == "TransactionProcessingCompleted"
    assert completed_call.kwargs["topic"] == KAFKA_TRANSACTION_PROCESSING_READY_TOPIC
    assert completed_call.kwargs["payload"]["readiness_reason"] == (
        "atomic_transaction_processing_completed"
    )
    assert completed_call.kwargs["payload"]["traceparent"] == (
        "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    )
    assert valuation_call.kwargs["aggregate_id"] == "PB-001:SEC-001:2026-04-10:4"
    assert valuation_call.kwargs["event_type"] == "PortfolioDayReadyForValuation"
    assert valuation_call.kwargs["topic"] == KAFKA_PORTFOLIO_SECURITY_DAY_VALUATION_READY_TOPIC
    assert valuation_call.kwargs["payload"]["traceparent"] == (
        "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    )


@pytest.mark.asyncio
async def test_stage_without_security_omits_valuation_readiness() -> None:
    outbox_repository = AsyncMock()
    stager = TransactionalTransactionReadinessEventStager(outbox_repository)

    await stager.stage_transaction_readiness(
        _stage(security_id=None),
        correlation_id=None,
        traceparent=None,
    )

    outbox_repository.create_outbox_event.assert_awaited_once()
    assert outbox_repository.create_outbox_event.await_args.kwargs["event_type"] == (
        "TransactionProcessingCompleted"
    )
