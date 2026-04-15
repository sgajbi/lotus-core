from decimal import Decimal

import pytest
from portfolio_common.analytics_cashflow_semantics import (
    classify_analytics_cash_flow,
    normalize_position_flow_amount,
)


@pytest.mark.parametrize(
    ("classification", "amount", "expected"),
    [
        ("INVESTMENT_OUTFLOW", Decimal("-5000"), Decimal("5000")),
        ("INVESTMENT_INFLOW", Decimal("5000"), Decimal("-5000")),
        ("INCOME", Decimal("12.34"), Decimal("-12.34")),
        ("CASHFLOW_IN", Decimal("100"), Decimal("100")),
        ("EXPENSE", Decimal("-25"), Decimal("-25")),
    ],
)
def test_normalize_position_flow_amount(classification: str, amount: Decimal, expected: Decimal):
    assert normalize_position_flow_amount(amount=amount, classification=classification) == expected


@pytest.mark.parametrize(
    ("classification", "is_position_flow", "is_portfolio_flow", "expected"),
    [
        ("CASHFLOW_IN", True, True, ("external_flow", "external")),
        ("CASHFLOW_OUT", True, True, ("external_flow", "external")),
        ("INVESTMENT_OUTFLOW", True, False, ("internal_trade_flow", "internal")),
        ("INVESTMENT_INFLOW", True, False, ("internal_trade_flow", "internal")),
        ("FX_BUY", True, False, ("internal_trade_flow", "internal")),
        ("FX_SELL", True, False, ("internal_trade_flow", "internal")),
        ("INTERNAL", True, True, ("internal_trade_flow", "internal")),
        ("TRANSFER", True, False, ("internal_trade_flow", "internal")),
        ("TRANSFER", False, True, ("transfer", "external")),
        ("TRANSFER", False, False, ("transfer", "internal")),
        ("INCOME", True, True, ("income", "operational")),
        ("EXPENSE", True, True, ("fee", "operational")),
        ("UNKNOWN_CLASSIFICATION", False, False, ("other", "operational")),
    ],
)
def test_classify_analytics_cash_flow(
    classification: str,
    is_position_flow: bool,
    is_portfolio_flow: bool,
    expected: tuple[str, str],
):
    assert (
        classify_analytics_cash_flow(
            classification=classification,
            is_position_flow=is_position_flow,
            is_portfolio_flow=is_portfolio_flow,
        )
        == expected
    )
