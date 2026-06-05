from decimal import Decimal

import pytest
from portfolio_common.valuation_prices import resolve_valuation_unit_price


def test_resolve_valuation_unit_price_preserves_equity_price():
    assert resolve_valuation_unit_price(
        market_price=Decimal("101.25"),
        quantity=Decimal("180"),
        cost_basis_local=Decimal("178704"),
        product_type="EQUITY",
    ) == Decimal("101.25")


def test_resolve_valuation_unit_price_aligns_legacy_bond_percent_quotes():
    assert resolve_valuation_unit_price(
        market_price=Decimal("101.35"),
        quantity=Decimal("180"),
        cost_basis_local=Decimal("178704"),
        product_type="bond",
    ) == Decimal("1013.50")


def test_resolve_valuation_unit_price_preserves_bond_price_already_in_unit_terms():
    assert resolve_valuation_unit_price(
        market_price=Decimal("1013.5"),
        quantity=Decimal("180"),
        cost_basis_local=Decimal("178704"),
        product_type="Bond",
    ) == Decimal("1013.5")


def test_resolve_valuation_unit_price_preserves_zero_quantity_bond_price():
    assert resolve_valuation_unit_price(
        market_price=Decimal("101.35"),
        quantity=Decimal("0"),
        cost_basis_local=Decimal("178704"),
        product_type="bond",
    ) == Decimal("101.35")


def test_resolve_valuation_unit_price_accepts_stringable_numeric_inputs():
    assert resolve_valuation_unit_price(
        market_price="101.35",
        quantity="180",
        cost_basis_local="178704",
        product_type="bond",
    ) == Decimal("1013.50")


def test_resolve_valuation_unit_price_rejects_missing_required_values():
    with pytest.raises(ValueError, match="market_price is required"):
        resolve_valuation_unit_price(
            market_price=" ",
            quantity=Decimal("180"),
            cost_basis_local=Decimal("178704"),
            product_type="bond",
        )
