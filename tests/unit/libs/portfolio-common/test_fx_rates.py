from decimal import Decimal

from portfolio_common.fx_rates import coerce_positive_fx_rate_or_none


def test_coerce_positive_fx_rate_accepts_decimal_and_string_inputs():
    assert coerce_positive_fx_rate_or_none(Decimal("1.0825")) == Decimal("1.0825")
    assert coerce_positive_fx_rate_or_none("1.0825") == Decimal("1.0825")


def test_coerce_positive_fx_rate_rejects_missing_zero_negative_and_invalid_inputs():
    assert coerce_positive_fx_rate_or_none(None) is None
    assert coerce_positive_fx_rate_or_none(Decimal("0")) is None
    assert coerce_positive_fx_rate_or_none(Decimal("-1.1")) is None
    assert coerce_positive_fx_rate_or_none("not-a-rate") is None
