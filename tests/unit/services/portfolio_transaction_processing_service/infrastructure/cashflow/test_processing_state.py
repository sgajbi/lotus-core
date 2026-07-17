"""Test SQL-backed epoch and semantic cashflow state."""

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from portfolio_common.idempotency_repository import IdempotencyRepository
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.infrastructure.cashflow import (
    CASHFLOW_PROCESSING_SERVICE_NAME,
    SqlAlchemyCashflowProcessingState,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cashflow import (
    processing_state as state_module,
)

pytestmark = pytest.mark.asyncio


def _transaction() -> BookedTransaction:
    return BookedTransaction(
        transaction_id="TX-001",
        portfolio_id="PB-001",
        instrument_id="INST-001",
        security_id="SEC-001",
        transaction_date=datetime(2026, 4, 10, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("25"),
        gross_transaction_amount=Decimal("250"),
        trade_currency="SGD",
        currency="SGD",
        epoch=3,
    )


async def test_processing_state_checks_epoch_with_cashflow_service_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class AcceptingEpochFencer:
        def __init__(self, session: AsyncSession, *, service_name: str) -> None:
            captured.update(session=session, service_name=service_name)

        async def check(self, event: object) -> bool:
            captured["event"] = event
            return True

    monkeypatch.setattr(state_module, "EpochFencer", AcceptingEpochFencer)
    session = AsyncMock(spec=AsyncSession)
    state = SqlAlchemyCashflowProcessingState(
        session,
        AsyncMock(spec=IdempotencyRepository),
        source_topic="transactions.persisted",
    )

    accepted = await state.accepts_epoch(
        _transaction(),
        correlation_id="corr-001",
        traceparent="trace-001",
    )

    assert accepted is True
    assert captured["session"] is session
    assert captured["service_name"] == CASHFLOW_PROCESSING_SERVICE_NAME
    event = captured["event"]
    assert getattr(event, "correlation_id") == "corr-001"
    assert getattr(event, "traceparent") == "trace-001"


@pytest.mark.parametrize(
    ("message_epoch", "locked_position_epoch", "expected"),
    [(None, 3, True), (3, 3, True), (4, 3, True), (2, 3, False)],
)
async def test_processing_state_reuses_write_locked_position_epoch_without_database_lookup(
    monkeypatch: pytest.MonkeyPatch,
    message_epoch: int | None,
    locked_position_epoch: int,
    expected: bool,
) -> None:
    class UnexpectedEpochFencer:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("database epoch fence must not be rebuilt while row lock is held")

    monkeypatch.setattr(state_module, "EpochFencer", UnexpectedEpochFencer)
    state = SqlAlchemyCashflowProcessingState(
        AsyncMock(spec=AsyncSession),
        AsyncMock(spec=IdempotencyRepository),
        source_topic="transactions.persisted",
    )

    accepted = await state.accepts_epoch(
        replace(_transaction(), epoch=message_epoch),
        correlation_id="corr-001",
        traceparent="trace-001",
        locked_position_epoch=locked_position_epoch,
    )

    assert accepted is expected


async def test_processing_state_claims_semantic_cashflow_identity() -> None:
    repository = AsyncMock(spec=IdempotencyRepository)
    repository.claim_event_processing.return_value = True
    state = SqlAlchemyCashflowProcessingState(
        AsyncMock(spec=AsyncSession),
        repository,
        source_topic="transactions.persisted",
    )

    claimed = await state.claim_semantic_event(
        _transaction(),
        event_id="transactions.persisted-0-42",
        semantic_event_id="cashflow:PB-001:TX-001:3",
        correlation_id="corr-001",
    )

    assert claimed is True
    repository.claim_event_processing.assert_awaited_once_with(
        "cashflow:PB-001:TX-001:3",
        "PB-001",
        CASHFLOW_PROCESSING_SERVICE_NAME,
        "corr-001",
    )
