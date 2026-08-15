"""Tests for product-level quote-authority requirements."""

from decimal import Decimal

import pytest
from portfolio_common.domain.valuation import requires_bond_quote_authority


@pytest.mark.parametrize("product_type", ["BOND", "Bond", " bond "])
def test_non_flat_bond_requires_explicit_quote_authority(product_type: str) -> None:
    assert requires_bond_quote_authority(
        product_type=product_type,
        quantity=Decimal("10"),
    )


def test_flat_bond_is_quote_independent() -> None:
    assert not requires_bond_quote_authority(
        product_type="BOND",
        quantity=Decimal("0"),
    )


@pytest.mark.parametrize("product_type", [None, "", "EQUITY", "FUND"])
def test_non_bond_does_not_require_bond_quote_authority(product_type: str | None) -> None:
    assert not requires_bond_quote_authority(
        product_type=product_type,
        quantity=Decimal("10"),
    )


def test_quote_authority_rule_rejects_missing_quantity() -> None:
    with pytest.raises(ValueError, match="quantity is required"):
        requires_bond_quote_authority(product_type="BOND", quantity=" ")
