from decimal import Decimal

from portfolio_common.decimal_amounts import required_decimal


def resolve_valuation_unit_price(
    *,
    market_price: object,
    quantity: object,
    cost_basis_local: object,
    product_type: str | None,
) -> Decimal:
    """Resolve the unit price used by valuation and reconciliation calculations."""
    valuation_price_local = required_decimal(market_price, field_name="market_price")
    quantity_amount = required_decimal(quantity, field_name="quantity")
    if not _should_normalize_bond_percent_quote(product_type, quantity_amount):
        return valuation_price_local

    local_cost_basis = required_decimal(cost_basis_local, field_name="cost_basis_local")
    multiplier = _bond_percent_quote_multiplier(
        valuation_price_local=valuation_price_local,
        average_cost_local=abs(local_cost_basis / quantity_amount),
    )
    return valuation_price_local * multiplier


def _should_normalize_bond_percent_quote(
    product_type: str | None,
    quantity_amount: Decimal,
) -> bool:
    return _normalized_product_type(product_type) == "BOND" and not quantity_amount.is_zero()


def _normalized_product_type(product_type: str | None) -> str:
    return (product_type or "").strip().upper()


def _bond_percent_quote_multiplier(
    *,
    valuation_price_local: Decimal,
    average_cost_local: Decimal,
) -> Decimal:
    absolute_price_local = abs(valuation_price_local)
    if not _looks_like_legacy_bond_percent_quote(absolute_price_local, average_cost_local):
        return Decimal("1")
    price_ratio = average_cost_local / absolute_price_local
    return _bond_price_ratio_multiplier(price_ratio)


def _looks_like_legacy_bond_percent_quote(
    absolute_price_local: Decimal,
    average_cost_local: Decimal,
) -> bool:
    return (
        absolute_price_local > Decimal("0")
        and absolute_price_local < Decimal("200")
        and average_cost_local >= Decimal("500")
    )


def _bond_price_ratio_multiplier(price_ratio: Decimal) -> Decimal:
    if price_ratio >= Decimal("50"):
        return Decimal("100")
    if price_ratio >= Decimal("5"):
        return Decimal("10")
    return Decimal("1")
