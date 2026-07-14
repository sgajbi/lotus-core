"""Tests for governed cashflow staging inside transaction processing."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from portfolio_common.events import TransactionEvent
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.domain.cashflow import (
    CalculatedCashflow,
    StoredCashflow,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    CachedCashflowRule,
    CashflowCalculationWorkflow,
    LinkedCashLegError,
    cashflow_calculated_event_from_stored_cashflow,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    cashflow_staging_workflow as workflow_module,
)

pytestmark = pytest.mark.asyncio


async def test_linked_cash_leg_contract_rejects_missing_upstream_reference() -> None:
    event = TransactionEvent(
        transaction_id="TX-INVALID-LINK",
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
        cash_entry_mode="UPSTREAM_PROVIDED",
    )

    with pytest.raises(LinkedCashLegError):
        await CashflowCalculationWorkflow()._stage_cashflow_processing(
            db=AsyncMock(spec=AsyncSession),
            cashflow_repo=AsyncMock(),
            outbox_repo=AsyncMock(),
            event=event,
            correlation_id="corr-001",
        )


async def test_completion_event_preserves_corporate_action_lineage() -> None:
    source = TransactionEvent(
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
        economic_event_id="EVENT-001",
        linked_transaction_group_id="GROUP-001",
        parent_event_reference="PARENT-001",
        linked_cash_transaction_id="CASH-001",
    )
    saved = StoredCashflow(
        cashflow_id=91,
        transaction_id=source.transaction_id,
        portfolio_id=source.portfolio_id,
        security_id=source.security_id,
        cashflow_date=date(2026, 5, 3),
        amount=Decimal("275"),
        currency="USD",
        classification="CORPORATE_ACTION_PROCEEDS",
        timing="EOD",
        calculation_type="NET",
        is_position_flow=True,
        is_portfolio_flow=False,
        economic_event_id=source.economic_event_id,
        linked_transaction_group_id=source.linked_transaction_group_id,
        epoch=0,
    )

    event = cashflow_calculated_event_from_stored_cashflow(saved, source)

    assert event.economic_event_id == "EVENT-001"
    assert event.linked_transaction_group_id == "GROUP-001"
    assert event.parent_event_reference == "PARENT-001"
    assert event.linked_cash_transaction_id == "CASH-001"


async def test_stage_cashflow_calculation_persists_domain_result_and_publishes_event() -> None:
    source = TransactionEvent(
        transaction_id="TX-STAGE-001",
        portfolio_id="PB-001",
        instrument_id="INST-001",
        security_id="SEC-001",
        transaction_date=datetime(2026, 4, 10, tzinfo=timezone.utc),
        settlement_date=datetime(2026, 4, 12, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("25"),
        gross_transaction_amount=Decimal("250"),
        trade_fee=Decimal("2"),
        trade_currency="SGD",
        currency="SGD",
        economic_event_id="EVENT-001",
        linked_transaction_group_id="GROUP-001",
        epoch=3,
    )
    stored = StoredCashflow(
        cashflow_id=92,
        transaction_id=source.transaction_id,
        portfolio_id=source.portfolio_id,
        security_id=source.security_id,
        cashflow_date=date(2026, 4, 12),
        amount=Decimal("-252"),
        currency="SGD",
        classification="INVESTMENT_OUTFLOW",
        timing="BOD",
        calculation_type="NET",
        is_position_flow=True,
        is_portfolio_flow=False,
        economic_event_id="EVENT-001",
        linked_transaction_group_id="GROUP-001",
        epoch=3,
    )
    repository = AsyncMock()
    repository.create.return_value = stored
    outbox_repository = AsyncMock()
    rule = CachedCashflowRule(
        classification="INVESTMENT_OUTFLOW",
        timing="BOD",
        is_position_flow=True,
        is_portfolio_flow=False,
        rule_set_version="rules-v1",
        rule_set_effective_at_utc=None,
    )

    record_count = await workflow_module._stage_cashflow_calculation(
        repository,
        outbox_repository,
        source,
        workflow_module.to_booked_transaction(source),
        rule,
        "corr-001",
        False,
    )

    calculated = repository.create.await_args.args[0]
    assert isinstance(calculated, CalculatedCashflow)
    assert calculated.amount == Decimal("-252")
    assert calculated.cashflow_date == date(2026, 4, 12)
    assert calculated.epoch == 3
    outbox_call = outbox_repository.create_outbox_event.await_args.kwargs
    assert outbox_call["topic"] == "cashflows.calculated"
    assert outbox_call["payload"]["cashflow_id"] == 92
    assert outbox_call["correlation_id"] == "corr-001"
    assert record_count == 1
