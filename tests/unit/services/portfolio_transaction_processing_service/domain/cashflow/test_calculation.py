"""Characterize cashflow policy through canonical event mapping."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from portfolio_common.events import TransactionEvent

from src.services.portfolio_transaction_processing_service.app.domain.cashflow import (
    CalculatedCashflow,
    CashflowClassification,
    CashflowRule,
    CashflowTiming,
    calculate_transaction_cashflow,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_mapping.booked_transaction import (  # noqa: E501
    to_booked_transaction,
)


@pytest.fixture
def base_transaction_event() -> TransactionEvent:
    """Provides a base, schema-valid transaction event that can be customized in tests."""
    return TransactionEvent(
        transaction_id="TXN_CASHFLOW_01",
        portfolio_id="PORT_CF_01",
        instrument_id="INST_CF_01",
        security_id="SEC_CF_01",
        transaction_date=datetime(2025, 8, 1, 10, 0, 0),
        transaction_type="BUY",  # Default type
        quantity=Decimal("100"),
        price=Decimal("10"),
        gross_transaction_amount=Decimal("1000"),
        trade_fee=Decimal("5.50"),
        trade_currency="USD",
        currency="USD",
    )


def _calculate(event: TransactionEvent, rule: CashflowRule) -> CalculatedCashflow:
    """Map the framework event once, then exercise the canonical domain policy."""
    return calculate_transaction_cashflow(to_booked_transaction(event), rule)


def test_calculate_buy_transaction(base_transaction_event: TransactionEvent):
    """A BUY is a negative cashflow (outflow)."""
    # ARRANGE
    event = base_transaction_event
    rule = CashflowRule(
        classification=CashflowClassification.INVESTMENT_OUTFLOW,
        timing=CashflowTiming.BOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    # ACT
    cashflow = _calculate(event, rule)

    # ASSERT
    assert cashflow.amount < 0
    assert cashflow.amount == Decimal("-1005.50")
    assert cashflow.economic_event_id is None
    assert cashflow.linked_transaction_group_id is None
    assert cashflow.is_position_flow is True
    assert cashflow.is_portfolio_flow is False


def test_calculate_buy_transaction_normalizes_transaction_type(
    base_transaction_event: TransactionEvent,
):
    event = base_transaction_event.model_copy(update={"transaction_type": " buy "})
    rule = CashflowRule(
        classification=CashflowClassification.INVESTMENT_OUTFLOW,
        timing=CashflowTiming.BOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    cashflow = _calculate(event, rule)

    assert cashflow.amount == Decimal("-1005.50")


def test_calculate_rejects_post_validation_negative_trade_fee(
    base_transaction_event: TransactionEvent,
):
    event = base_transaction_event
    event.trade_fee = Decimal("-0.01")
    rule = CashflowRule(
        classification=CashflowClassification.INVESTMENT_OUTFLOW,
        timing=CashflowTiming.BOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    with pytest.raises(ValueError, match="trade_fee"):
        _calculate(event, rule)


def test_calculate_rejects_post_validation_negative_fee_component(
    base_transaction_event: TransactionEvent,
):
    event = base_transaction_event
    event.brokerage = Decimal("-0.01")
    rule = CashflowRule(
        classification=CashflowClassification.INVESTMENT_OUTFLOW,
        timing=CashflowTiming.BOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    with pytest.raises(ValueError, match="brokerage"):
        _calculate(event, rule)


def test_calculate_sell_transaction(base_transaction_event: TransactionEvent):
    """A SELL is a positive cashflow (inflow)."""
    # ARRANGE
    event = base_transaction_event
    event.transaction_type = "SELL"
    rule = CashflowRule(
        classification=CashflowClassification.INVESTMENT_INFLOW,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    # ACT
    cashflow = _calculate(event, rule)

    # ASSERT
    assert cashflow.amount > 0
    assert cashflow.amount == Decimal("994.50")
    assert cashflow.is_position_flow is True
    assert cashflow.is_portfolio_flow is False


@pytest.mark.parametrize(
    ("transaction_type", "classification"),
    [
        ("BUY", CashflowClassification.INVESTMENT_OUTFLOW),
        ("SELL", CashflowClassification.INVESTMENT_INFLOW),
        ("DEPOSIT", CashflowClassification.CASHFLOW_IN),
        ("WITHDRAWAL", CashflowClassification.CASHFLOW_OUT),
        ("FX_CASH_SETTLEMENT_BUY", CashflowClassification.FX_BUY),
        ("FX_CASH_SETTLEMENT_SELL", CashflowClassification.FX_SELL),
    ],
)
def test_calculate_uses_settlement_date_for_settlement_dated_cashflows(
    base_transaction_event: TransactionEvent,
    transaction_type: str,
    classification: CashflowClassification,
):
    event = base_transaction_event.model_copy(
        update={
            "transaction_type": transaction_type,
            "transaction_date": datetime(2026, 4, 10, 10, 0, 0),
            "settlement_date": datetime(2026, 4, 12, 9, 30, 0),
            "trade_fee": Decimal("0"),
        }
    )
    rule = CashflowRule(
        classification=classification,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=transaction_type in {"DEPOSIT", "WITHDRAWAL"},
    )

    cashflow = _calculate(event, rule)

    assert cashflow.cashflow_date == date(2026, 4, 12)


@pytest.mark.parametrize("transaction_type", ["DIVIDEND", "INTEREST"])
def test_calculate_uses_settlement_date_as_income_payment_value_date_proxy(
    base_transaction_event: TransactionEvent,
    transaction_type: str,
):
    event = base_transaction_event.model_copy(
        update={
            "transaction_type": transaction_type,
            "transaction_date": datetime(2026, 1, 20, 10, 0, 0),
            "settlement_date": datetime(2026, 1, 25, 9, 30, 0),
            "quantity": Decimal("0"),
            "price": Decimal("0"),
            "trade_fee": Decimal("0"),
        }
    )
    rule = CashflowRule(
        classification=CashflowClassification.INCOME,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    cashflow = _calculate(event, rule)

    assert cashflow.cashflow_date == date(2026, 1, 25)


def test_calculate_uses_synthetic_flow_effective_date_before_settlement_date(
    base_transaction_event: TransactionEvent,
):
    event = base_transaction_event.model_copy(
        update={
            "transaction_type": "CASH_IN_LIEU",
            "transaction_date": datetime(2026, 5, 1, 10, 0, 0),
            "settlement_date": datetime(2026, 5, 5, 9, 30, 0),
            "synthetic_flow_effective_date": date(2026, 5, 3),
            "has_synthetic_flow": True,
            "synthetic_flow_amount_local": Decimal("-1000"),
            "synthetic_flow_currency": "USD",
            "synthetic_flow_classification": "POSITION_CASH_IN_LIEU_OUT",
        }
    )
    rule = CashflowRule(
        classification=CashflowClassification.TRANSFER,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    cashflow = _calculate(event, rule)

    assert cashflow.cashflow_date == date(2026, 5, 3)


@pytest.mark.parametrize(
    ("transaction_type", "synthetic_amount", "expected_amount"),
    [
        ("EXCHANGE_OUT", Decimal("-1500"), Decimal("-1500")),
        ("EXCHANGE_IN", Decimal("1500"), Decimal("1500")),
    ],
)
def test_calculate_transfer_uses_explicit_synthetic_market_value_economics(
    base_transaction_event: TransactionEvent,
    transaction_type: str,
    synthetic_amount: Decimal,
    expected_amount: Decimal,
) -> None:
    event = base_transaction_event.model_copy(
        update={
            "transaction_type": transaction_type,
            "gross_transaction_amount": Decimal("900"),
            "trade_fee": Decimal("0"),
            "has_synthetic_flow": True,
            "synthetic_flow_effective_date": date(2026, 5, 3),
            "synthetic_flow_amount_local": synthetic_amount,
            "synthetic_flow_currency": "EUR",
            "synthetic_flow_classification": (
                "POSITION_TRANSFER_OUT"
                if transaction_type.endswith("_OUT")
                else "POSITION_TRANSFER_IN"
            ),
        }
    )
    rule = CashflowRule(
        classification=CashflowClassification.TRANSFER,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    cashflow = _calculate(event, rule)

    assert cashflow.amount == expected_amount
    assert cashflow.amount != event.gross_transaction_amount
    assert cashflow.currency == "EUR"
    assert cashflow.cashflow_date == date(2026, 5, 3)
    assert cashflow.calculation_type == "MVT"
    assert cashflow.is_position_flow is True
    assert cashflow.is_portfolio_flow is False


def test_calculate_cash_consideration_remains_real_net_cashflow(
    base_transaction_event: TransactionEvent,
) -> None:
    event = base_transaction_event.model_copy(
        update={
            "transaction_type": "CASH_CONSIDERATION",
            "gross_transaction_amount": Decimal("275"),
            "trade_fee": Decimal("0"),
            "has_synthetic_flow": False,
            "economic_event_id": "EVT-MIXED-01",
            "linked_transaction_group_id": "GROUP-MIXED-01",
            "linked_cash_transaction_id": "CASH-SETTLEMENT-01",
        }
    )
    rule = CashflowRule(
        classification=CashflowClassification.CORPORATE_ACTION_PROCEEDS,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    cashflow = _calculate(event, rule)

    assert cashflow.amount == Decimal("275")
    assert cashflow.classification == "CORPORATE_ACTION_PROCEEDS"
    assert cashflow.currency == "USD"
    assert cashflow.calculation_type == "NET"
    assert cashflow.economic_event_id == "EVT-MIXED-01"
    assert cashflow.linked_transaction_group_id == "GROUP-MIXED-01"


@pytest.mark.parametrize(
    ("event_update", "rule_update", "message"),
    [
        (
            {"synthetic_flow_amount_local": None},
            {},
            "amount is required",
        ),
        (
            {"synthetic_flow_currency": None},
            {},
            "currency is required",
        ),
        (
            {"synthetic_flow_amount_local": Decimal("1500")},
            {},
            "sign does not match",
        ),
        (
            {},
            {"is_portfolio_flow": True},
            "position-level and non-portfolio",
        ),
    ],
)
def test_calculate_rejects_invalid_synthetic_position_flow_contract(
    base_transaction_event: TransactionEvent,
    event_update: dict[str, object],
    rule_update: dict[str, object],
    message: str,
) -> None:
    event = base_transaction_event.model_copy(
        update={
            "transaction_type": "EXCHANGE_OUT",
            "trade_fee": Decimal("0"),
            "has_synthetic_flow": True,
            "synthetic_flow_effective_date": date(2026, 5, 3),
            "synthetic_flow_amount_local": Decimal("-1500"),
            "synthetic_flow_currency": "USD",
            "synthetic_flow_classification": "POSITION_TRANSFER_OUT",
            **event_update,
        }
    )
    rule_values = {
        "classification": CashflowClassification.TRANSFER,
        "timing": CashflowTiming.EOD,
        "is_position_flow": True,
        "is_portfolio_flow": False,
        **rule_update,
    }
    rule = CashflowRule(**rule_values)

    with pytest.raises(ValueError, match=message):
        _calculate(event, rule)


@pytest.mark.parametrize(
    "target_amounts",
    [
        [Decimal("1500")],
        [Decimal("900"), Decimal("600")],
    ],
)
def test_linked_internal_position_transfer_market_values_sum_to_zero(
    base_transaction_event: TransactionEvent,
    target_amounts: list[Decimal],
) -> None:
    common = {
        "gross_transaction_amount": Decimal("900"),
        "trade_fee": Decimal("0"),
        "has_synthetic_flow": True,
        "synthetic_flow_effective_date": date(2026, 5, 3),
        "synthetic_flow_currency": "USD",
        "economic_event_id": "EVT-TRANSFER-01",
        "linked_transaction_group_id": "GROUP-TRANSFER-01",
    }
    events = [
        base_transaction_event.model_copy(
            update={
                **common,
                "transaction_id": "TRANSFER-SOURCE-OUT",
                "transaction_type": "DEMERGER_OUT",
                "synthetic_flow_amount_local": Decimal("-1500"),
                "synthetic_flow_classification": "POSITION_TRANSFER_OUT",
            }
        ),
        *[
            base_transaction_event.model_copy(
                update={
                    **common,
                    "transaction_id": f"TRANSFER-TARGET-IN-{index}",
                    "transaction_type": "DEMERGER_IN",
                    "synthetic_flow_amount_local": amount,
                    "synthetic_flow_classification": "POSITION_TRANSFER_IN",
                }
            )
            for index, amount in enumerate(target_amounts, start=1)
        ],
    ]
    rule = CashflowRule(
        classification=CashflowClassification.TRANSFER,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    transfer_flows = [_calculate(event, rule) for event in events]

    assert sum(flow.amount for flow in transfer_flows) == Decimal("0")
    assert all(flow.calculation_type == "MVT" for flow in transfer_flows)
    assert all(flow.is_position_flow for flow in transfer_flows)
    assert not any(flow.is_portfolio_flow for flow in transfer_flows)
    assert {flow.linked_transaction_group_id for flow in transfer_flows} == {"GROUP-TRANSFER-01"}


def test_corporate_action_cash_settlement_is_excluded_from_flow_levels(
    base_transaction_event: TransactionEvent,
) -> None:
    settlement = base_transaction_event.model_copy(
        update={
            "transaction_id": "CASH-SETTLEMENT-01",
            "instrument_id": "CASH-USD",
            "security_id": "CASH-USD",
            "transaction_type": "ADJUSTMENT",
            "quantity": Decimal("0"),
            "price": Decimal("0"),
            "gross_transaction_amount": Decimal("275"),
            "trade_fee": Decimal("0"),
            "movement_direction": "INFLOW",
            "originating_transaction_id": "CASH-CONSIDERATION-01",
            "originating_transaction_type": "CASH_CONSIDERATION",
            "link_type": "CASH_CONSIDERATION_TO_CASH",
            "economic_event_id": "EVT-MIXED-01",
            "linked_transaction_group_id": "GROUP-MIXED-01",
        }
    )
    legacy_adjustment_rule = CashflowRule(
        classification=CashflowClassification.TRANSFER,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    cashflow = _calculate(settlement, legacy_adjustment_rule)

    assert cashflow.amount == Decimal("275")
    assert cashflow.is_position_flow is False
    assert cashflow.is_portfolio_flow is False
    assert cashflow.economic_event_id == "EVT-MIXED-01"
    assert cashflow.linked_transaction_group_id == "GROUP-MIXED-01"


@pytest.mark.parametrize(
    ("originating_transaction_type", "movement_direction", "expected_amount"),
    [
        ("BUY", "OUTFLOW", Decimal("-275")),
        ("SELL", "INFLOW", Decimal("275")),
    ],
)
def test_linked_trade_cash_settlement_remains_a_position_flow(
    base_transaction_event: TransactionEvent,
    originating_transaction_type: str,
    movement_direction: str,
    expected_amount: Decimal,
) -> None:
    settlement = base_transaction_event.model_copy(
        update={
            "transaction_id": f"{originating_transaction_type}-CASH-SETTLEMENT-01",
            "instrument_id": "CASH-USD",
            "security_id": "CASH-USD",
            "transaction_type": "ADJUSTMENT",
            "quantity": Decimal("0"),
            "price": Decimal("0"),
            "gross_transaction_amount": Decimal("275"),
            "trade_fee": Decimal("0"),
            "movement_direction": movement_direction,
            "originating_transaction_id": f"{originating_transaction_type}-01",
            "originating_transaction_type": originating_transaction_type,
            "link_type": f"{originating_transaction_type}_TO_CASH",
        }
    )
    adjustment_rule = CashflowRule(
        classification=CashflowClassification.TRANSFER,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    cashflow = _calculate(settlement, adjustment_rule)

    assert cashflow.amount == expected_amount
    assert cashflow.is_position_flow is True
    assert cashflow.is_portfolio_flow is False


def test_calculate_falls_back_to_transaction_date_when_policy_source_date_missing(
    base_transaction_event: TransactionEvent,
):
    event = base_transaction_event.model_copy(
        update={
            "transaction_type": "BUY",
            "transaction_date": datetime(2026, 4, 10, 10, 0, 0),
            "settlement_date": None,
        }
    )
    rule = CashflowRule(
        classification=CashflowClassification.INVESTMENT_OUTFLOW,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    cashflow = _calculate(event, rule)

    assert cashflow.cashflow_date == date(2026, 4, 10)


def test_calculate_dividend_transaction(base_transaction_event: TransactionEvent):
    """A DIVIDEND is a positive cashflow (inflow)."""
    # ARRANGE
    event = base_transaction_event
    event.transaction_type = "DIVIDEND"
    rule = CashflowRule(
        classification=CashflowClassification.INCOME,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    # ACT
    cashflow = _calculate(event, rule)

    # ASSERT
    assert cashflow.amount > 0
    assert cashflow.is_position_flow is True
    assert cashflow.is_portfolio_flow is False
    assert cashflow.timing == "EOD"


def test_calculate_interest_income_transaction(base_transaction_event: TransactionEvent):
    """INTEREST INCOME is a positive cashflow (inflow)."""
    event = base_transaction_event.model_copy(
        update={
            "transaction_type": "INTEREST",
            "gross_transaction_amount": Decimal("120"),
            "trade_fee": Decimal("5"),
            "interest_direction": "INCOME",
        }
    )
    rule = CashflowRule(
        classification=CashflowClassification.INCOME,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    cashflow = _calculate(event, rule)

    assert cashflow.amount == Decimal("115")
    assert cashflow.amount > 0


@pytest.mark.parametrize("net_interest_amount", [None, Decimal("1187.00")])
def test_calculate_interest_income_is_invariant_to_explicit_net_interest(
    base_transaction_event: TransactionEvent,
    net_interest_amount: Decimal | None,
):
    """INTEREST should apply the fee once after resolving the pre-fee net amount."""
    event = base_transaction_event.model_copy(
        update={
            "transaction_type": "INTEREST",
            "gross_transaction_amount": Decimal("1280.75"),
            "withholding_tax_amount": Decimal("81.75"),
            "other_interest_deductions_amount": Decimal("12.00"),
            "net_interest_amount": net_interest_amount,
            "interest_direction": "INCOME",
        }
    )
    rule = CashflowRule(
        classification=CashflowClassification.INCOME,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    cashflow = _calculate(event, rule)

    assert cashflow.amount == Decimal("1181.50")
    assert cashflow.amount > 0


def test_calculate_interest_expense_transaction(base_transaction_event: TransactionEvent):
    """INTEREST EXPENSE is a negative cashflow (outflow)."""
    event = base_transaction_event.model_copy(
        update={
            "transaction_type": "INTEREST",
            "gross_transaction_amount": Decimal("120"),
            "trade_fee": Decimal("5"),
            "interest_direction": "EXPENSE",
        }
    )
    rule = CashflowRule(
        classification=CashflowClassification.INCOME,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    cashflow = _calculate(event, rule)

    assert cashflow.amount == Decimal("-125")
    assert cashflow.amount < 0


def test_calculate_interest_expense_normalizes_direction(base_transaction_event: TransactionEvent):
    event = base_transaction_event.model_copy(
        update={
            "transaction_type": " interest ",
            "gross_transaction_amount": Decimal("120"),
            "trade_fee": Decimal("5"),
            "interest_direction": " expense ",
        }
    )
    rule = CashflowRule(
        classification=CashflowClassification.INCOME,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    cashflow = _calculate(event, rule)

    assert cashflow.amount == Decimal("-125")


def test_calculate_deposit_transaction(base_transaction_event: TransactionEvent):
    """A DEPOSIT is a positive cashflow (inflow)."""
    # ARRANGE
    event = base_transaction_event
    event.transaction_type = "DEPOSIT"
    rule = CashflowRule(
        classification=CashflowClassification.CASHFLOW_IN,
        timing=CashflowTiming.BOD,
        is_position_flow=True,
        is_portfolio_flow=True,
    )

    # ACT
    cashflow = _calculate(event, rule)

    # ASSERT
    assert cashflow.classification == "CASHFLOW_IN"
    assert cashflow.is_position_flow is True
    assert cashflow.is_portfolio_flow is True
    assert cashflow.amount > 0


def test_calculate_fee_transaction(base_transaction_event: TransactionEvent):
    """A FEE is a negative cashflow (outflow)."""
    # ARRANGE
    event = base_transaction_event
    event.transaction_type = "FEE"
    rule = CashflowRule(
        classification=CashflowClassification.EXPENSE,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=True,
    )

    # ACT
    cashflow = _calculate(event, rule)

    # ASSERT
    assert cashflow.amount < 0
    assert cashflow.is_position_flow is True
    assert cashflow.is_portfolio_flow is True


def test_calculate_withdrawal_transaction(base_transaction_event: TransactionEvent):
    """A WITHDRAWAL is a negative cashflow (outflow)."""
    # ARRANGE
    event = base_transaction_event
    event.transaction_type = "WITHDRAWAL"
    event.gross_transaction_amount = Decimal("5000")
    event.trade_fee = Decimal("0")
    rule = CashflowRule(
        classification=CashflowClassification.CASHFLOW_OUT,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=True,
    )

    # ACT
    cashflow = _calculate(event, rule)

    # ASSERT
    assert cashflow.amount == -event.gross_transaction_amount
    assert cashflow.classification == "CASHFLOW_OUT"
    assert cashflow.timing == "EOD"
    assert cashflow.is_position_flow is True
    assert cashflow.is_portfolio_flow is True


def test_calculate_transfer_in_transaction(base_transaction_event: TransactionEvent):
    """A TRANSFER_IN is a positive cashflow (inflow)."""
    # ARRANGE
    event = base_transaction_event
    event.transaction_type = "TRANSFER_IN"
    rule = CashflowRule(
        classification=CashflowClassification.TRANSFER,
        timing=CashflowTiming.BOD,
        is_position_flow=True,
        is_portfolio_flow=True,
    )

    # ACT
    cashflow = _calculate(event, rule)

    # ASSERT
    assert cashflow.classification == "TRANSFER"
    assert cashflow.is_portfolio_flow is True
    assert cashflow.amount > 0


def test_calculate_transfer_out_transaction(base_transaction_event: TransactionEvent):
    """A TRANSFER_OUT is a negative cashflow (outflow)."""
    # ARRANGE
    event = base_transaction_event
    event.transaction_type = "TRANSFER_OUT"
    rule = CashflowRule(
        classification=CashflowClassification.TRANSFER,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=True,
    )

    # ACT
    cashflow = _calculate(event, rule)

    # ASSERT
    assert cashflow.classification == "TRANSFER"
    assert cashflow.is_portfolio_flow is True
    assert cashflow.amount < 0


def test_calculate_transfer_out_normalizes_transaction_type(
    base_transaction_event: TransactionEvent,
):
    event = base_transaction_event.model_copy(update={"transaction_type": " transfer_out "})
    rule = CashflowRule(
        classification=CashflowClassification.TRANSFER,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=True,
    )

    cashflow = _calculate(event, rule)

    assert cashflow.amount == Decimal("-994.50")
    assert cashflow.classification == "TRANSFER"


@pytest.mark.parametrize(
    ("transaction_type", "expected_sign"),
    [
        ("SPLIT", Decimal("1")),
        ("BONUS_ISSUE", Decimal("1")),
        ("STOCK_DIVIDEND", Decimal("1")),
        ("RIGHTS_ALLOCATE", Decimal("1")),
        ("RIGHTS_SHARE_DELIVERY", Decimal("1")),
        ("RIGHTS_REFUND", Decimal("1")),
        ("REVERSE_SPLIT", Decimal("-1")),
        ("CONSOLIDATION", Decimal("-1")),
        ("RIGHTS_SUBSCRIBE", Decimal("-1")),
        ("RIGHTS_OVERSUBSCRIBE", Decimal("-1")),
        ("RIGHTS_SELL", Decimal("-1")),
        ("RIGHTS_EXPIRE", Decimal("-1")),
    ],
)
def test_calculate_transfer_classification_for_ca_expansion_types(
    base_transaction_event: TransactionEvent,
    transaction_type: str,
    expected_sign: Decimal,
):
    event = base_transaction_event.model_copy(update={"transaction_type": transaction_type})
    rule = CashflowRule(
        classification=CashflowClassification.TRANSFER,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    cashflow = _calculate(event, rule)
    assert cashflow.amount * expected_sign > 0


@pytest.mark.parametrize(
    ("transaction_type", "quantity", "expected_sign"),
    [
        ("RIGHTS_ADJUSTMENT", Decimal("10"), Decimal("1")),
        ("RIGHTS_ADJUSTMENT", Decimal("-10"), Decimal("-1")),
        ("CASH_IN_LIEU", Decimal("10"), Decimal("1")),
        ("CASH_IN_LIEU", Decimal("-10"), Decimal("-1")),
    ],
)
def test_calculate_transfer_fallback_sign_uses_quantity_for_unmapped_transfer_type(
    base_transaction_event: TransactionEvent,
    transaction_type: str,
    quantity: Decimal,
    expected_sign: Decimal,
):
    """
    For TRANSFER-classified types not explicitly mapped as in/out,
    sign must follow quantity direction.
    """
    event = base_transaction_event.model_copy(
        update={
            "transaction_type": transaction_type,
            "quantity": quantity,
            "trade_fee": Decimal("0"),
        }
    )
    rule = CashflowRule(
        classification=CashflowClassification.TRANSFER,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    cashflow = _calculate(event, rule)
    assert cashflow.amount * expected_sign > 0


def test_calculate_buy_propagates_linkage_metadata(base_transaction_event: TransactionEvent):
    """BUY cashflow should carry economic-event linkage metadata for reconciliation."""
    event = base_transaction_event
    event.economic_event_id = "EVT-2026-9001"
    event.linked_transaction_group_id = "LTG-2026-9001"
    rule = CashflowRule(
        classification=CashflowClassification.INVESTMENT_OUTFLOW,
        timing=CashflowTiming.BOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    cashflow = _calculate(event, rule)

    assert cashflow.economic_event_id == "EVT-2026-9001"
    assert cashflow.linked_transaction_group_id == "LTG-2026-9001"


def test_calculate_adjustment_inflow_uses_movement_direction(
    base_transaction_event: TransactionEvent,
):
    event = base_transaction_event.model_copy(
        update={
            "transaction_type": "ADJUSTMENT",
            "movement_direction": "INFLOW",
            "gross_transaction_amount": Decimal("250"),
            "trade_fee": Decimal("0"),
        }
    )
    rule = CashflowRule(
        classification=CashflowClassification.TRANSFER,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    cashflow = _calculate(event, rule)
    assert cashflow.amount == Decimal("250")
    assert cashflow.amount > 0


def test_calculate_adjustment_outflow_uses_movement_direction(
    base_transaction_event: TransactionEvent,
):
    event = base_transaction_event.model_copy(
        update={
            "transaction_type": "ADJUSTMENT",
            "movement_direction": "OUTFLOW",
            "gross_transaction_amount": Decimal("250"),
            "trade_fee": Decimal("0"),
        }
    )
    rule = CashflowRule(
        classification=CashflowClassification.TRANSFER,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    cashflow = _calculate(event, rule)
    assert cashflow.amount == Decimal("-250")
    assert cashflow.amount < 0


def test_calculate_fx_cash_settlement_buy_is_positive(base_transaction_event: TransactionEvent):
    event = base_transaction_event.model_copy(
        update={
            "transaction_type": "FX_CASH_SETTLEMENT_BUY",
            "gross_transaction_amount": Decimal("13450"),
            "trade_fee": Decimal("0"),
            "currency": "SGD",
        }
    )
    rule = CashflowRule(
        classification=CashflowClassification.FX_BUY,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    cashflow = _calculate(event, rule)
    assert cashflow.amount == Decimal("13450")
    assert cashflow.classification == "FX_BUY"
    assert cashflow.is_position_flow is True
    assert cashflow.is_portfolio_flow is False


def test_calculate_fx_cash_settlement_sell_is_negative(base_transaction_event: TransactionEvent):
    event = base_transaction_event.model_copy(
        update={
            "transaction_type": "FX_CASH_SETTLEMENT_SELL",
            "gross_transaction_amount": Decimal("10000"),
            "trade_fee": Decimal("0"),
            "currency": "USD",
        }
    )
    rule = CashflowRule(
        classification=CashflowClassification.FX_SELL,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    cashflow = _calculate(event, rule)
    assert cashflow.amount == Decimal("-10000")
    assert cashflow.classification == "FX_SELL"
    assert cashflow.is_position_flow is True
    assert cashflow.is_portfolio_flow is False


@pytest.mark.parametrize(
    ("transaction_type", "classification"),
    [
        ("FX_CASH_SETTLEMENT_BUY", CashflowClassification.FX_BUY),
        ("FX_CASH_SETTLEMENT_SELL", CashflowClassification.FX_SELL),
    ],
)
@pytest.mark.parametrize("trade_fee", [Decimal("1"), Decimal("10000"), Decimal("10001")])
def test_calculate_fx_cash_settlement_rejects_embedded_fee_before_sign_normalization(
    base_transaction_event: TransactionEvent,
    transaction_type: str,
    classification: CashflowClassification,
    trade_fee: Decimal,
) -> None:
    event = base_transaction_event.model_copy(
        update={
            "transaction_type": transaction_type,
            "gross_transaction_amount": Decimal("10000"),
            "trade_fee": trade_fee,
        }
    )
    rule = CashflowRule(
        classification=classification,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    with pytest.raises(ValueError, match="FX_025_NON_ZERO_EMBEDDED_FEE: trade_fee"):
        _calculate(event, rule)


@pytest.mark.parametrize(
    ("transaction_type", "classification"),
    [
        ("FX_CASH_SETTLEMENT_BUY", CashflowClassification.FX_BUY),
        ("FX_CASH_SETTLEMENT_SELL", CashflowClassification.FX_SELL),
    ],
)
@pytest.mark.parametrize(
    "withholding_tax_amount", [Decimal("1"), Decimal("10000"), Decimal("10001")]
)
def test_calculate_fx_cash_settlement_rejects_embedded_tax_before_sign_normalization(
    base_transaction_event: TransactionEvent,
    transaction_type: str,
    classification: CashflowClassification,
    withholding_tax_amount: Decimal,
) -> None:
    event = base_transaction_event.model_copy(
        update={
            "transaction_type": transaction_type,
            "gross_transaction_amount": Decimal("10000"),
            "withholding_tax_amount": withholding_tax_amount,
        }
    )
    rule = CashflowRule(
        classification=classification,
        timing=CashflowTiming.EOD,
        is_position_flow=True,
        is_portfolio_flow=False,
    )

    with pytest.raises(
        ValueError,
        match="FX_026_NON_ZERO_EMBEDDED_TAX: withholding_tax_amount",
    ):
        _calculate(event, rule)
