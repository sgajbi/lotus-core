"""Test transactional staging of calculated cashflow events."""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from portfolio_common.outbox_repository import OutboxRepository

from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.domain.cashflow import StoredCashflow
from src.services.portfolio_transaction_processing_service.app.infrastructure.cashflow import (
    TransactionalCashflowEventStager,
    cashflow_calculated_event,
)


def _source_transaction() -> BookedTransaction:
    return BookedTransaction(
        transaction_id="CA-CASH-01",
        portfolio_id="PB-001",
        instrument_id="INST-001",
        security_id="SEC-001",
        transaction_date=datetime(2026, 5, 3, tzinfo=timezone.utc),
        transaction_type="CASH_CONSIDERATION",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("275"),
        trade_currency="USD",
        currency="USD",
        parent_event_reference="PARENT-001",
        linked_cash_transaction_id="CASH-001",
    )


def _stored_cashflow() -> StoredCashflow:
    return StoredCashflow(
        cashflow_id=91,
        transaction_id="CA-CASH-01",
        portfolio_id="PB-001",
        security_id="SEC-001",
        cashflow_date=date(2026, 5, 3),
        amount=Decimal("275"),
        currency="USD",
        classification="CORPORATE_ACTION_PROCEEDS",
        timing="EOD",
        calculation_type="NET",
        is_position_flow=True,
        is_portfolio_flow=False,
        economic_event_id="EVENT-001",
        linked_transaction_group_id="GROUP-001",
        epoch=0,
    )


def test_event_mapper_preserves_cashflow_and_source_lineage() -> None:
    event = cashflow_calculated_event(_stored_cashflow(), _source_transaction())

    assert event.economic_event_id == "EVENT-001"
    assert event.linked_transaction_group_id == "GROUP-001"
    assert event.parent_event_reference == "PARENT-001"
    assert event.linked_cash_transaction_id == "CASH-001"


@pytest.mark.asyncio
async def test_event_stager_writes_governed_outbox_contract() -> None:
    repository = AsyncMock(spec=OutboxRepository)
    stager = TransactionalCashflowEventStager(repository)

    await stager.stage_calculated_cashflow(
        _stored_cashflow(),
        _source_transaction(),
        correlation_id="corr-001",
    )

    call = repository.create_outbox_event.await_args.kwargs
    assert call["aggregate_type"] == "Cashflow"
    assert call["aggregate_id"] == "PB-001"
    assert call["partition_key"].value == "PB-001"
    assert call["event_type"] == "CashflowCalculated"
    assert call["topic"] == "cashflows.calculated"
    assert call["payload"]["cashflow_id"] == 91
    assert call["correlation_id"] == "corr-001"
