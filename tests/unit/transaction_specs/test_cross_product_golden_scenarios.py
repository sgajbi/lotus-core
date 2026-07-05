from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from portfolio_common.database_models import CashflowRule
from portfolio_common.events import TransactionEvent
from portfolio_common.transaction_domain import evaluate_ca_bundle_a_reconciliation

from src.services.calculators.cashflow_calculator_service.app.core.cashflow_logic import (
    CashflowLogic,
)
from src.services.calculators.cashflow_calculator_service.app.core.enums import (
    CashflowClassification,
    CashflowTiming,
)
from src.services.calculators.position_calculator.app.core.position_logic import PositionCalculator
from src.services.calculators.position_calculator.app.core.position_models import (
    PositionState as PositionStateDTO,
)

FIXTURE_PATH = Path("tests/fixtures/cross-product-transaction-golden-scenarios.v1.json")


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _scenario(scenario_id: str) -> dict:
    return next(item for item in _fixture()["scenarios"] if item["id"] == scenario_id)


def _event(
    raw: dict, *, net_cost: str | None = None, quantity: str | None = None
) -> TransactionEvent:
    return TransactionEvent(
        transaction_id=raw["transaction_id"],
        portfolio_id=raw["portfolio_id"],
        instrument_id=raw["security_id"],
        security_id=raw["security_id"],
        transaction_date=datetime(2026, 4, 10, 10, 0, 0),
        transaction_type=raw["transaction_type"],
        quantity=Decimal(quantity or raw.get("quantity", "0")),
        price=Decimal(raw.get("price", "0")),
        gross_transaction_amount=Decimal(raw.get("gross_transaction_amount", "0")),
        trade_fee=Decimal(raw.get("trade_fee", "0")),
        trade_currency=raw.get("trade_currency", "USD"),
        currency=raw.get("trade_currency", "USD"),
        net_cost=Decimal(net_cost if net_cost is not None else raw.get("net_cost", "0")),
        net_cost_local=Decimal(net_cost if net_cost is not None else raw.get("net_cost", "0")),
        correlation_id=raw.get("correlation_id"),
        parent_event_reference=raw.get("parent_event_reference"),
        linked_transaction_group_id=raw.get("linked_transaction_group_id"),
    )


def test_equity_buy_sell_golden_position_and_cost_relief() -> None:
    scenario = _scenario("equity_buy_sell_fee_tax_fx")
    buy, sell = scenario["input_events"]
    state = PositionStateDTO(
        quantity=Decimal("0"), cost_basis=Decimal("0"), cost_basis_local=Decimal("0")
    )

    after_buy = PositionCalculator.calculate_next_position(state, _event(buy, net_cost="1000"))
    after_sell = PositionCalculator.calculate_next_position(
        after_buy, _event(sell, net_cost="-400")
    )

    expected = scenario["expected"]
    assert after_sell.quantity == Decimal(expected["position_state"]["quantity"])
    assert after_sell.cost_basis == Decimal(expected["position_state"]["cost_basis"])
    assert after_sell.cost_basis_local == Decimal(expected["position_state"]["cost_basis_local"])
    assert Decimal(expected["cost_basis_impact"]["realized_gain_loss"]) == Decimal("93")


def test_dividend_golden_cashflow_preserves_position_and_income_amount(monkeypatch) -> None:
    scenario = _scenario("equity_dividend_stock_split_return_of_capital_spin_off_merger_rights")
    dividend = scenario["input_events"][0]
    monkeypatch.setattr(
        "src.services.calculators.cashflow_calculator_service.app.core.cashflow_logic.CASHFLOWS_CREATED_TOTAL",
        type(
            "Metric",
            (),
            {"labels": lambda self, **_: type("Inc", (), {"inc": lambda self: None})()},
        )(),
    )

    state = PositionStateDTO(
        quantity=Decimal("10"),
        cost_basis=Decimal("1000"),
        cost_basis_local=Decimal("1000"),
    )
    event = _event(dividend)
    next_state = PositionCalculator.calculate_next_position(state, event)
    cashflow = CashflowLogic.calculate(
        event,
        CashflowRule(
            classification=CashflowClassification.INCOME,
            timing=CashflowTiming.EOD,
            is_position_flow=True,
            is_portfolio_flow=False,
        ),
    )

    assert next_state.quantity == Decimal("10")
    assert next_state.cost_basis == Decimal("1000")
    assert cashflow.amount == Decimal(scenario["expected"]["income_cashflow_impact"]["amount"])
    assert cashflow.classification == "INCOME"


def test_transfer_golden_position_and_cost_delta() -> None:
    scenario = _scenario("transfer_in_out_linked_lots_custody_account_movement")
    transfer_in, transfer_out = scenario["input_events"]
    state = PositionStateDTO(
        quantity=Decimal("100"),
        cost_basis=Decimal("100"),
        cost_basis_local=Decimal("100"),
    )

    after_in = PositionCalculator.calculate_next_position(state, _event(transfer_in))
    after_out = PositionCalculator.calculate_next_position(after_in, _event(transfer_out))

    assert after_out.quantity == Decimal("99")
    assert after_out.cost_basis == Decimal("105")
    assert scenario["expected"]["lineage"]["idempotency_key"] == "transaction_id"


def test_ca_bundle_golden_spin_off_reconciles_basis_transfer() -> None:
    scenario = _scenario("equity_dividend_stock_split_return_of_capital_spin_off_merger_rights")
    source_out, target_in = scenario["input_events"][1:]

    result = evaluate_ca_bundle_a_reconciliation(
        [
            _event(source_out),
            _event(target_in),
        ]
    )

    assert result.status == "balanced"
    assert result.net_basis_delta_local == Decimal("0")
