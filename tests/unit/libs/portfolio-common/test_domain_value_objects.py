from datetime import date
from decimal import Decimal

import pytest
from portfolio_common.domain_value_objects import (
    CurrencyCode,
    FxRate,
    MoneyAmount,
    UnitPrice,
)


def test_currency_code_normalizes_and_compares_by_iso_value() -> None:
    assert CurrencyCode.from_raw(" usd ") == CurrencyCode.from_raw("USD")
    assert str(CurrencyCode.from_raw("sgd")) == "SGD"


def test_money_amount_quantizes_with_half_up_rounding_and_serializes_at_boundary() -> None:
    money = MoneyAmount.from_raw(amount="12.345", currency="usd").quantized()

    assert money.amount == Decimal("12.35")
    assert money.currency == CurrencyCode("USD")
    assert money.as_boundary_payload() == {"amount": "12.35", "currency": "USD"}


def test_money_amount_optional_from_raw_skips_missing_amount_before_currency_validation() -> None:
    assert MoneyAmount.optional_from_raw(amount=None, currency=None) is None


def test_money_amount_requires_currency_when_amount_is_present() -> None:
    with pytest.raises(ValueError, match="Currency code must be a string"):
        MoneyAmount.optional_from_raw(amount="10", currency=None)


def test_fx_rate_identity_and_cross_currency_conversion() -> None:
    same_currency_rate = FxRate.for_pair(
        from_currency=" usd ",
        to_currency="USD",
        rate=None,
        as_of_date=date(2026, 3, 8),
    )
    cross_currency_rate = FxRate.from_raw(
        from_currency="eur",
        to_currency="sgd",
        rate="1.45",
        as_of_date=date(2026, 3, 8),
    )

    assert same_currency_rate.rate == Decimal("1")
    assert same_currency_rate.from_currency == CurrencyCode("USD")
    assert same_currency_rate.to_currency == CurrencyCode("USD")
    assert MoneyAmount.from_raw(amount="100", currency="EUR").converted(
        cross_currency_rate
    ) == MoneyAmount(amount=Decimal("145.00"), currency=CurrencyCode("SGD"))


def test_fx_rate_rejects_missing_or_non_positive_cross_currency_rates() -> None:
    with pytest.raises(ValueError, match="fx_rate is required"):
        FxRate.from_raw(from_currency="EUR", to_currency="SGD", rate=None)

    with pytest.raises(ValueError, match="fx_rate must be positive"):
        FxRate.from_raw(from_currency="EUR", to_currency="SGD", rate="0")


def test_money_conversion_rejects_currency_basis_mismatch() -> None:
    rate = FxRate.from_raw(from_currency="EUR", to_currency="SGD", rate="1.45")

    with pytest.raises(ValueError, match="FX source currency mismatch"):
        MoneyAmount.from_raw(amount="100", currency="USD").converted(rate)


def test_unit_price_keeps_optional_currency_at_serialization_boundary() -> None:
    assert UnitPrice.from_raw(price="101.25").as_boundary_payload() == {"price": "101.25"}
    assert UnitPrice.from_raw(price="101.25", currency=" usd ").as_boundary_payload() == {
        "price": "101.25",
        "currency": "USD",
    }
