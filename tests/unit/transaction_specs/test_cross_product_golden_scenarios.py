from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from portfolio_common.database_models import CashflowRule
from portfolio_common.events import TransactionEvent
from portfolio_common.transaction_domain import evaluate_ca_bundle_a_reconciliation
from portfolio_common.transaction_type_registry import (
    TARGET_NOT_IMPLEMENTED,
    get_transaction_type_definition,
)

from src.services.calculators.cashflow_calculator_service.app.core.cashflow_logic import (
    CashflowLogic,
)
from src.services.calculators.cashflow_calculator_service.app.core.enums import (
    CashflowClassification,
    CashflowTiming,
)
from src.services.portfolio_transaction_processing_service.app.domain.position_reducer import (
    PositionBalanceState as PositionStateDTO,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.position_calculation_workflow import (  # noqa: E501
    PositionCalculationWorkflow,
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
        economic_event_id=raw.get("economic_event_id"),
        parent_event_reference=raw.get("parent_event_reference"),
        linked_transaction_group_id=raw.get("linked_transaction_group_id"),
        originating_transaction_id=raw.get("originating_transaction_id"),
        adjustment_reason=raw.get("adjustment_reason"),
    )


def test_equity_buy_sell_golden_position_and_cost_relief() -> None:
    scenario = _scenario("equity_buy_sell_fee_tax_fx")
    buy, sell = scenario["input_events"]
    state = PositionStateDTO(
        quantity=Decimal("0"), cost_basis=Decimal("0"), cost_basis_local=Decimal("0")
    )

    after_buy = PositionCalculationWorkflow.calculate_next_position(
        state, _event(buy, net_cost="1000")
    )
    after_sell = PositionCalculationWorkflow.calculate_next_position(
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
    next_state = PositionCalculationWorkflow.calculate_next_position(state, event)
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

    after_in = PositionCalculationWorkflow.calculate_next_position(state, _event(transfer_in))
    after_out = PositionCalculationWorkflow.calculate_next_position(after_in, _event(transfer_out))

    assert after_out.quantity == Decimal("99")
    assert after_out.cost_basis == Decimal("105")
    assert scenario["expected"]["lineage"]["idempotency_key"] == "transaction_id"


def test_fund_golden_subscription_distribution_reinvestment_and_redemption(
    monkeypatch,
) -> None:
    scenario = _scenario("fund_subscription_redemption_distribution_reinvestment")
    subscription, distribution, reinvestment, redemption = scenario["input_events"]
    monkeypatch.setattr(
        "src.services.calculators.cashflow_calculator_service.app.core.cashflow_logic.CASHFLOWS_CREATED_TOTAL",
        type(
            "Metric",
            (),
            {"labels": lambda self, **_: type("Inc", (), {"inc": lambda self: None})()},
        )(),
    )
    state = PositionStateDTO()

    after_subscription = PositionCalculationWorkflow.calculate_next_position(
        state, _event(subscription)
    )
    after_reinvestment = PositionCalculationWorkflow.calculate_next_position(
        after_subscription, _event(reinvestment)
    )
    after_redemption = PositionCalculationWorkflow.calculate_next_position(
        after_reinvestment, _event(redemption)
    )
    distribution_cashflow = CashflowLogic.calculate(
        _event(distribution),
        CashflowRule(
            classification=CashflowClassification.INCOME,
            timing=CashflowTiming.EOD,
            is_position_flow=True,
            is_portfolio_flow=False,
        ),
    )

    expected = scenario["expected"]
    assert after_redemption.quantity == Decimal(expected["position_state"]["quantity"])
    assert after_redemption.cost_basis == Decimal(expected["position_state"]["cost_basis"])
    assert distribution_cashflow.amount == Decimal(
        expected["income_cashflow_impact"]["distribution_amount"]
    )
    assert distribution_cashflow.classification == "INCOME"
    assert Decimal(expected["cash_ledger_impact"]["net_cash"]) == Decimal("-640")
    assert Decimal(expected["cost_basis_impact"]["realized_gain_loss"]) == Decimal("60")


def test_option_and_structured_product_golden_target_gap_and_coupon_cashflow(
    monkeypatch,
) -> None:
    scenario = _scenario("option_exercise_expiry_structured_coupon_barrier_payoff")
    exercise_out, exercise_in, structured_coupon = scenario["input_events"]
    monkeypatch.setattr(
        "src.services.calculators.cashflow_calculator_service.app.core.cashflow_logic.CASHFLOWS_CREATED_TOTAL",
        type(
            "Metric",
            (),
            {"labels": lambda self, **_: type("Inc", (), {"inc": lambda self: None})()},
        )(),
    )

    exercise_out_definition = get_transaction_type_definition(exercise_out["transaction_type"])
    exercise_in_definition = get_transaction_type_definition(exercise_in["transaction_type"])
    structured_coupon_state = PositionCalculationWorkflow.calculate_next_position(
        PositionStateDTO(quantity=Decimal("10"), cost_basis=Decimal("1000")),
        _event(structured_coupon),
    )
    structured_coupon_cashflow = CashflowLogic.calculate(
        _event(structured_coupon),
        CashflowRule(
            classification=CashflowClassification.INCOME,
            timing=CashflowTiming.EOD,
            is_position_flow=True,
            is_portfolio_flow=False,
        ),
    )

    assert exercise_out_definition is not None
    assert exercise_in_definition is not None
    assert exercise_out_definition.calculation_support_status == TARGET_NOT_IMPLEMENTED
    assert exercise_in_definition.calculation_support_status == TARGET_NOT_IMPLEMENTED
    assert exercise_out_definition.production_booking_allowed is False
    assert exercise_in_definition.production_booking_allowed is False
    assert structured_coupon_state.quantity == Decimal("10")
    assert structured_coupon_cashflow.amount == Decimal(
        scenario["expected"]["income_cashflow_impact"]["amount"]
    )
    assert structured_coupon_cashflow.classification == "INCOME"


def test_correction_golden_cancel_and_rebook_restates_position() -> None:
    scenario = _scenario("correction_cancel_rebook_restatement")
    original, cancel, rebook = scenario["input_events"]
    state = PositionStateDTO()

    after_original = PositionCalculationWorkflow.calculate_next_position(state, _event(original))
    after_cancel = PositionCalculationWorkflow.calculate_next_position(
        after_original, _event(cancel)
    )
    after_rebook = PositionCalculationWorkflow.calculate_next_position(after_cancel, _event(rebook))

    expected = scenario["expected"]
    assert after_original.quantity == Decimal("100")
    assert after_cancel.quantity == Decimal("0")
    assert after_cancel.cost_basis == Decimal("0")
    assert after_rebook.quantity == Decimal(expected["position_state"]["quantity"])
    assert after_rebook.cost_basis == Decimal(expected["position_state"]["cost_basis"])
    assert cancel["originating_transaction_id"] == original["transaction_id"]
    assert rebook["originating_transaction_id"] == original["transaction_id"]
    assert cancel["adjustment_reason"] == "CANCEL"
    assert rebook["adjustment_reason"] == "REBOOK"


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
