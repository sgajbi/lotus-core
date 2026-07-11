"""Tests for governed cashflow staging inside transaction processing."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from portfolio_common.database_models import CashflowRule
from portfolio_common.events import TransactionEvent
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.domain.cashflow import StoredCashflow
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    CashflowCalculationWorkflow,
    CashflowRuleSetVersion,
    LinkedCashLegError,
    SqlAlchemyCashflowRulesRepository,
    cashflow_calculated_event_from_stored_cashflow,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure import (
    cashflow_staging_workflow as workflow_module,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def reset_rule_cache() -> None:
    """Keep process-level cashflow rule cache state isolated between tests."""
    workflow_module._cashflow_rule_cache_state = None
    workflow_module._cashflow_rule_cache_lock = None


def _rule(*, timing: str = "BOD", updated_at: datetime | None = None) -> CashflowRule:
    return CashflowRule(
        transaction_type="BUY",
        classification="INVESTMENT_OUTFLOW",
        timing=timing,
        is_position_flow=True,
        is_portfolio_flow=False,
        updated_at=updated_at,
    )


async def test_concurrent_rule_requests_load_one_cache_snapshot() -> None:
    session = AsyncMock(spec=AsyncSession)
    repository = AsyncMock(spec=SqlAlchemyCashflowRulesRepository)
    repository.get_all_rules.return_value = [_rule()]
    repository.get_rule_set_version.return_value = CashflowRuleSetVersion(
        rule_count=1,
        latest_updated_at=None,
    )

    with (
        patch.object(workflow_module, "CASHFLOW_RULE_CACHE_TTL_SECONDS", 3600),
        patch.object(workflow_module, "SqlAlchemyCashflowRulesRepository", return_value=repository),
    ):
        first, second = await asyncio.gather(
            CashflowCalculationWorkflow()._get_rule_for_transaction(session, "BUY"),
            CashflowCalculationWorkflow()._get_rule_for_transaction(session, " buy "),
        )

    assert first == second
    assert first is not None
    assert repository.get_all_rules.await_count == 1


async def test_rule_cache_reloads_when_source_version_changes() -> None:
    first_version = datetime(2026, 4, 10, 8, tzinfo=timezone.utc)
    second_version = datetime(2026, 4, 10, 9, tzinfo=timezone.utc)
    repository = AsyncMock(spec=SqlAlchemyCashflowRulesRepository)
    repository.get_all_rules.side_effect = [
        [_rule(timing="BOD", updated_at=first_version)],
        [_rule(timing="EOD", updated_at=second_version)],
    ]
    repository.get_rule_set_version.side_effect = [
        CashflowRuleSetVersion(rule_count=1, latest_updated_at=second_version),
        CashflowRuleSetVersion(rule_count=1, latest_updated_at=second_version),
    ]

    with (
        patch.object(workflow_module, "CASHFLOW_RULE_CACHE_TTL_SECONDS", 3600),
        patch.object(workflow_module, "SqlAlchemyCashflowRulesRepository", return_value=repository),
    ):
        workflow = CashflowCalculationWorkflow()
        first = await workflow._get_rule_for_transaction(AsyncMock(spec=AsyncSession), "BUY")
        second = await workflow._get_rule_for_transaction(AsyncMock(spec=AsyncSession), "BUY")

    assert first is not None and first.timing == "BOD"
    assert second is not None and second.timing == "EOD"
    assert first.rule_set_version != second.rule_set_version
    assert second.rule_set_effective_at_utc == second_version


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
