"""Tests for product-level quote-authority requirements."""

from decimal import Decimal

import pytest
from portfolio_common.domain.valuation import (
    is_quote_independent_flat_position,
    requires_bond_quote_authority,
)


@pytest.mark.parametrize("product_type", ["BOND", "Bond", " bond "])
def test_non_flat_bond_requires_explicit_quote_authority(product_type: str) -> None:
    assert requires_bond_quote_authority(
        product_type=product_type,
        quantity=Decimal("10"),
        cost_basis_reporting=Decimal("10000"),
        cost_basis_local=Decimal("10000"),
    )


def test_flat_bond_is_quote_independent() -> None:
    assert not requires_bond_quote_authority(
        product_type="BOND",
        quantity=Decimal("0"),
        cost_basis_reporting=Decimal("0"),
        cost_basis_local=Decimal("0"),
    )


@pytest.mark.parametrize(
    ("cost_basis_reporting", "cost_basis_local"),
    [(Decimal("1"), Decimal("0")), (Decimal("0"), Decimal("1"))],
)
def test_zero_quantity_bond_with_residual_cost_requires_quote_authority(
    cost_basis_reporting: Decimal,
    cost_basis_local: Decimal,
) -> None:
    assert requires_bond_quote_authority(
        product_type="BOND",
        quantity=Decimal("0"),
        cost_basis_reporting=cost_basis_reporting,
        cost_basis_local=cost_basis_local,
    )


def test_quote_independent_flat_position_requires_zero_quantity_and_cost() -> None:
    assert is_quote_independent_flat_position(
        quantity=Decimal("0"),
        cost_basis_reporting=Decimal("0"),
        cost_basis_local=Decimal("0"),
    )


@pytest.mark.parametrize("product_type", [None, "", "EQUITY", "FUND"])
def test_non_bond_does_not_require_bond_quote_authority(product_type: str | None) -> None:
    assert not requires_bond_quote_authority(
        product_type=product_type,
        quantity=Decimal("10"),
        cost_basis_reporting=Decimal("10000"),
        cost_basis_local=Decimal("10000"),
    )


def test_quote_authority_rule_rejects_missing_quantity() -> None:
    with pytest.raises(ValueError, match="quantity is required"):
        requires_bond_quote_authority(
            product_type="BOND",
            quantity=" ",
            cost_basis_reporting=Decimal("0"),
            cost_basis_local=Decimal("0"),
        )
