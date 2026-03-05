# tests/unit/services/calculators/position-valuation-calculator/logic/test_valuation_logic.py
from decimal import Decimal

# Corrected absolute import
from src.services.calculators.position_valuation_calculator.app.logic.valuation_logic import (
    ValuationLogic,
)


def test_calculate_valuation_with_gain_same_currency():
    """
    Tests a standard valuation scenario resulting in an unrealized gain
    where all currencies (price, instrument, portfolio) are the same.
    """
    result = ValuationLogic.calculate_valuation(
        quantity=Decimal("100"),
        market_price=Decimal("120"),
        cost_basis_base=Decimal("10000"),
        cost_basis_local=Decimal("10000"),
        price_currency="USD",
        instrument_currency="USD",
        portfolio_currency="USD",
    )
    assert result is not None
    mv_base, mv_local, pnl_base, pnl_local = result

    # Expected MV = 100 * 120 = 12000
    assert mv_local == Decimal("12000")
    assert mv_base == Decimal("12000")
    # Expected UGL = 12000 - 10000 = 2000
    assert pnl_local == Decimal("2000")
    assert pnl_base == Decimal("2000")


def test_calculate_valuation_with_fx_conversion():
    """
    Tests a valuation scenario where the instrument/price is in EUR
    and the portfolio is in USD, requiring FX conversion.
    """
    result = ValuationLogic.calculate_valuation(
        quantity=Decimal("100"),  # 100 shares
        market_price=Decimal("120"),  # €120 per share
        cost_basis_local=Decimal("10000"),  # Total cost was €10,000
        cost_basis_base=Decimal("11000"),  # Total cost was $11,000 (at a 1.1 FX rate)
        price_currency="EUR",
        instrument_currency="EUR",
        portfolio_currency="USD",
        price_to_instrument_fx_rate=None,  # Price is already in instrument currency
        instrument_to_portfolio_fx_rate=Decimal("1.2"),  # Current FX rate is 1.2
    )
    assert result is not None
    mv_base, mv_local, pnl_base, pnl_local = result

    # Local (EUR) calculations
    assert mv_local == Decimal("12000")  # 100 shares * €120
    assert pnl_local == Decimal("2000")  # €12,000 MV - €10,000 cost

    # Base (USD) calculations
    assert mv_base == Decimal("14400")  # €12,000 MV * 1.2 FX rate
    assert pnl_base == Decimal("3400")  # $14,400 MV - $11,000 cost


def test_calculate_valuation_for_zero_quantity_position():
    """
    Tests that a zero-quantity position results in all zero valuation metrics.
    """
    result = ValuationLogic.calculate_valuation(
        quantity=Decimal("0"),
        market_price=Decimal("150"),
        cost_basis_base=Decimal("0"),
        cost_basis_local=Decimal("0"),
        price_currency="USD",
        instrument_currency="USD",
        portfolio_currency="USD",
    )
    assert result is not None
    mv_base, mv_local, pnl_base, pnl_local = result
    assert mv_base == Decimal("0")
    assert mv_local == Decimal("0")
    assert pnl_base == Decimal("0")
    assert pnl_local == Decimal("0")


def test_calculate_valuation_returns_none_if_fx_rate_missing():
    """
    Tests that the valuation fails (returns None) if a required FX rate is not provided.
    """
    # Scenario: Instrument(EUR) to Portfolio(USD) conversion is missing
    result = ValuationLogic.calculate_valuation(
        quantity=Decimal("100"),
        market_price=Decimal("120"),
        cost_basis_local=Decimal("10000"),
        cost_basis_base=Decimal("11000"),
        price_currency="EUR",
        instrument_currency="EUR",
        portfolio_currency="USD",
        instrument_to_portfolio_fx_rate=None,  # Missing rate
    )
    assert result is None


def test_calculate_valuation_with_price_currency_conversion():
    """
    Tests a full dual-FX conversion: Price(USD) -> Instrument(EUR) -> Portfolio(CHF).
    """
    result = ValuationLogic.calculate_valuation(
        quantity=Decimal("200"),
        market_price=Decimal("110"),  # Price is $110
        cost_basis_local=Decimal("20000"),  # Cost was €20,000
        cost_basis_base=Decimal("22000"),  # Cost was CHF 22,000
        price_currency="USD",
        instrument_currency="EUR",
        portfolio_currency="CHF",
        price_to_instrument_fx_rate=Decimal("0.90"),  # 1 USD = 0.90 EUR
        instrument_to_portfolio_fx_rate=Decimal("0.95"),  # 1 EUR = 0.95 CHF
    )
    assert result is not None
    mv_base, mv_local, pnl_base, pnl_local = result

    # 1. Price in local (EUR): $110 * 0.90 EUR/USD = €99
    # 2. Market Value in local (EUR): 200 shares * €99 = €19,800
    assert mv_local == Decimal("19800")
    # 3. PnL in local (EUR): €19,800 - €20,000 = -€200
    assert pnl_local == Decimal("-200")

    # 4. Market Value in base (CHF): €19,800 * 0.95 CHF/EUR = CHF 18,810
    assert mv_base == Decimal("18810")
    # 5. PnL in base (CHF): CHF 18,810 - CHF 22,000 = -CHF 3,190
    assert pnl_base == Decimal("-3190")


def test_calculate_valuation_with_loss_same_currency():
    """
    Tests a valuation scenario resulting in an unrealized loss
    where all currencies are the same.
    """
    result = ValuationLogic.calculate_valuation(
        quantity=Decimal("100"),
        market_price=Decimal("90"),
        cost_basis_base=Decimal("10000"),
        cost_basis_local=Decimal("10000"),
        price_currency="USD",
        instrument_currency="USD",
        portfolio_currency="USD",
    )
    assert result is not None
    mv_base, mv_local, pnl_base, pnl_local = result

    # Expected MV = 100 * 90 = 9000
    assert mv_local == Decimal("9000")
    assert mv_base == Decimal("9000")
    # Expected UGL = 9000 - 10000 = -1000
    assert pnl_local == Decimal("-1000")
    assert pnl_base == Decimal("-1000")


def test_calculate_valuation_with_fx_conversion_and_loss():
    """
    Tests a valuation scenario with FX conversion resulting in a loss in both currencies.
    """
    result = ValuationLogic.calculate_valuation(
        quantity=Decimal("100"),
        market_price=Decimal("95"),  # €95 per share
        cost_basis_local=Decimal("10000"),  # Total cost was €10,000
        cost_basis_base=Decimal("11000"),  # Total cost was $11,000 (at a 1.1 FX rate)
        price_currency="EUR",
        instrument_currency="EUR",
        portfolio_currency="USD",
        instrument_to_portfolio_fx_rate=Decimal("1.05"),  # Current FX rate is 1.05
    )
    assert result is not None
    mv_base, mv_local, pnl_base, pnl_local = result

    # Local (EUR) calculations
    assert mv_local == Decimal("9500")  # 100 shares * €95
    assert pnl_local == Decimal("-500")  # €9,500 MV - €10,000 cost

    # Base (USD) calculations
    assert mv_base == Decimal("9975")  # €9,500 MV * 1.05 FX rate
    assert pnl_base == Decimal("-1025")  # $9,975 MV - $11,000 cost


def test_calculate_valuation_price_conversion_only():
    """
    Tests a scenario where only the price needs conversion to the instrument currency,
    which is the same as the portfolio's base currency.
    """
    result = ValuationLogic.calculate_valuation(
        quantity=Decimal("100"),
        market_price=Decimal("80"),  # Price is £80
        cost_basis_local=Decimal("10000"),  # Cost was $10,000
        cost_basis_base=Decimal("10000"),  # Cost was $10,000
        price_currency="GBP",
        instrument_currency="USD",
        portfolio_currency="USD",
        price_to_instrument_fx_rate=Decimal("1.25"),  # 1 GBP = 1.25 USD
        instrument_to_portfolio_fx_rate=None,  # Should not be needed
    )
    assert result is not None
    mv_base, mv_local, pnl_base, pnl_local = result

    # Price in local (USD) = £80 * 1.25 = $100
    # Market Value in local (USD) = 100 shares * $100 = $10,000
    assert mv_local == Decimal("10000")
    # PnL in local (USD) = $10,000 - $10,000 = $0
    assert pnl_local == Decimal("0")

    # Base currency is the same as local
    assert mv_base == mv_local
    assert pnl_base == pnl_local
