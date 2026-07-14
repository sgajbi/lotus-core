"""Test application-owned transaction cashflow coordination."""

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.services.portfolio_transaction_processing_service.app.application import (
    ProcessTransactionCashflowUseCase,
    TransactionProcessingError,
    TransactionProcessingRejected,
)
from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.domain.cashflow import (
    CashflowCalculationContext,
    CashflowRule,
    StoredCashflow,
)
from src.services.portfolio_transaction_processing_service.app.ports.cashflow import (
    CashflowEventStagingPort,
    CashflowPersistencePort,
    CashflowProcessingStatePort,
    CashflowRuleResolutionPort,
)

pytestmark = pytest.mark.asyncio


def _transaction(**overrides: object) -> BookedTransaction:
    transaction = BookedTransaction(
        transaction_id="TX-001",
        portfolio_id="PB-001",
        instrument_id="INST-001",
        security_id="SEC-001",
        transaction_date=datetime(2026, 4, 10, 9, 30, tzinfo=timezone.utc),
        settlement_date=datetime(2026, 4, 12, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("25"),
        gross_transaction_amount=Decimal("250"),
        trade_currency="SGD",
        currency="SGD",
        trade_fee=Decimal("2"),
        epoch=3,
    )
    return replace(transaction, **overrides)


def _stored_cashflow(transaction: BookedTransaction) -> StoredCashflow:
    settlement_date = transaction.settlement_date
    assert settlement_date is not None
    return StoredCashflow(
        cashflow_id=91,
        transaction_id=transaction.transaction_id,
        portfolio_id=transaction.portfolio_id,
        security_id=transaction.security_id,
        cashflow_date=settlement_date.date(),
        amount=Decimal("-252"),
        currency="SGD",
        classification="INVESTMENT_OUTFLOW",
        timing="BOD",
        calculation_type="NET",
        is_position_flow=True,
        is_portfolio_flow=False,
        economic_event_id=None,
        linked_transaction_group_id=None,
        epoch=3,
    )


def _use_case() -> tuple[
    ProcessTransactionCashflowUseCase,
    AsyncMock,
    AsyncMock,
    AsyncMock,
    AsyncMock,
]:
    rules = AsyncMock(spec=CashflowRuleResolutionPort)
    state = AsyncMock(spec=CashflowProcessingStatePort)
    persistence = AsyncMock(spec=CashflowPersistencePort)
    events = AsyncMock(spec=CashflowEventStagingPort)
    state.accepts_epoch.return_value = True
    state.claim_semantic_event.return_value = True
    rules.resolve.return_value = CashflowRule(
        classification="INVESTMENT_OUTFLOW",
        timing="BOD",
        is_position_flow=True,
        is_portfolio_flow=False,
    )
    return (
        ProcessTransactionCashflowUseCase(
            rules=rules,
            state=state,
            persistence=persistence,
            events=events,
        ),
        rules,
        state,
        persistence,
        events,
    )


async def test_use_case_calculates_persists_and_stages_cashflow() -> None:
    use_case, rules, state, persistence, events = _use_case()
    transaction = _transaction()
    stored = _stored_cashflow(transaction)
    persistence.create.return_value = stored

    result = await use_case.execute(
        transaction,
        event_id="transactions.persisted-0-42",
        correlation_id="corr-001",
        traceparent="trace-001",
    )

    assert result.cashflow_record_count == 1
    state.accepts_epoch.assert_awaited_once_with(
        transaction,
        correlation_id="corr-001",
        traceparent="trace-001",
    )
    assert state.claim_semantic_event.await_args.kwargs["semantic_event_id"] == (
        "cashflow:PB-001:TX-001:3"
    )
    rules.resolve.assert_awaited_once_with("BUY")
    calculated = persistence.create.await_args.args[0]
    assert calculated.amount == Decimal("-252")
    assert calculated.cashflow_date == transaction.settlement_date.date()
    events.stage_calculated_cashflow.assert_awaited_once_with(
        stored,
        transaction,
        correlation_id="corr-001",
    )


async def test_use_case_returns_no_effect_for_semantic_duplicate() -> None:
    use_case, rules, state, persistence, events = _use_case()
    state.claim_semantic_event.return_value = False

    result = await use_case.execute(
        _transaction(),
        event_id="transactions.persisted-0-42",
        correlation_id=None,
        traceparent=None,
    )

    assert result.cashflow_record_count == 0
    rules.resolve.assert_not_awaited()
    persistence.create.assert_not_awaited()
    events.stage_calculated_cashflow.assert_not_awaited()


async def test_repair_replaces_cashflow_without_semantic_reclaim() -> None:
    use_case, _rules, state, persistence, events = _use_case()
    transaction = _transaction()
    stored = _stored_cashflow(transaction)
    persistence.replace.return_value = stored

    result = await use_case.execute(
        transaction,
        event_id="transactions.persisted-0-42",
        correlation_id="corr-repair",
        traceparent=None,
        repair_existing=True,
        calculation_context=CashflowCalculationContext.HISTORICAL_REBUILD,
    )

    assert result.cashflow_record_count == 1
    state.claim_semantic_event.assert_not_awaited()
    persistence.create.assert_not_awaited()
    persistence.replace.assert_awaited_once()
    events.stage_calculated_cashflow.assert_awaited_once()


async def test_use_case_rejects_stale_epoch_before_other_effects() -> None:
    use_case, rules, state, persistence, events = _use_case()
    state.accepts_epoch.return_value = False

    with pytest.raises(TransactionProcessingRejected) as raised:
        await use_case.execute(
            _transaction(),
            event_id="transactions.persisted-0-42",
            correlation_id=None,
            traceparent=None,
        )

    assert raised.value.reason_code == "cashflow_epoch_rejected"
    state.claim_semantic_event.assert_not_awaited()
    rules.resolve.assert_not_awaited()
    persistence.create.assert_not_awaited()
    events.stage_calculated_cashflow.assert_not_awaited()


async def test_use_case_maps_missing_rule_to_terminal_processing_error() -> None:
    use_case, rules, _state, persistence, events = _use_case()
    rules.resolve.return_value = None

    with pytest.raises(TransactionProcessingError) as raised:
        await use_case.execute(
            _transaction(),
            event_id="transactions.persisted-0-42",
            correlation_id=None,
            traceparent=None,
        )

    assert raised.value.reason_code == "cashflow_rule_missing"
    assert raised.value.retryable is False
    persistence.create.assert_not_awaited()
    events.stage_calculated_cashflow.assert_not_awaited()


async def test_use_case_maps_missing_linked_cash_leg_to_terminal_error() -> None:
    use_case, rules, _state, persistence, events = _use_case()

    with pytest.raises(TransactionProcessingError) as raised:
        await use_case.execute(
            _transaction(cash_entry_mode="UPSTREAM_PROVIDED"),
            event_id="transactions.persisted-0-42",
            correlation_id=None,
            traceparent=None,
        )

    assert raised.value.reason_code == "cashflow_contract_invalid"
    assert raised.value.retryable is False
    rules.resolve.assert_not_awaited()
    persistence.create.assert_not_awaited()
    events.stage_calculated_cashflow.assert_not_awaited()


async def test_use_case_maps_invalid_settlement_economics_to_governed_rejection() -> None:
    use_case, _rules, _state, persistence, events = _use_case()

    with pytest.raises(TransactionProcessingRejected) as raised:
        await use_case.execute(
            _transaction(
                transaction_type="DIVIDEND",
                gross_transaction_amount=Decimal("10"),
                trade_fee=Decimal("11"),
            ),
            event_id="transactions.persisted-0-42",
            correlation_id=None,
            traceparent=None,
        )

    assert raised.value.reason_code == "DIVIDEND_013_NON_POSITIVE_NET_SETTLEMENT"
    assert raised.value.detail["net_settlement_amount"] == "-1"
    persistence.create.assert_not_awaited()
    events.stage_calculated_cashflow.assert_not_awaited()


async def test_non_cashflow_fx_lifecycle_returns_no_effect_after_claim() -> None:
    use_case, rules, state, persistence, events = _use_case()

    result = await use_case.execute(
        _transaction(transaction_type="FX_FORWARD", component_type="FX_CONTRACT_OPEN"),
        event_id="transactions.persisted-0-42",
        correlation_id=None,
        traceparent=None,
    )

    assert result.cashflow_record_count == 0
    state.claim_semantic_event.assert_awaited_once()
    rules.resolve.assert_not_awaited()
    persistence.create.assert_not_awaited()
    events.stage_calculated_cashflow.assert_not_awaited()
