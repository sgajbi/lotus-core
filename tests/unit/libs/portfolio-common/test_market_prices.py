from decimal import Decimal

from portfolio_common.market_prices import coerce_positive_market_price_or_none


def test_coerce_positive_market_price_accepts_decimal_and_string_inputs():
    assert coerce_positive_market_price_or_none(Decimal("101.25")) == Decimal("101.25")
    assert coerce_positive_market_price_or_none("101.25") == Decimal("101.25")


def test_coerce_positive_market_price_rejects_missing_zero_negative_and_invalid_inputs():
    assert coerce_positive_market_price_or_none(None) is None
    assert coerce_positive_market_price_or_none(Decimal("0")) is None
    assert coerce_positive_market_price_or_none(Decimal("-101.25")) is None
    assert coerce_positive_market_price_or_none("not-a-price") is None
