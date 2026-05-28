from decimal import Decimal


def _as_decimal(value: object) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def resolve_valuation_unit_price(
    *,
    market_price: object,
    quantity: object,
    cost_basis_local: object,
    product_type: str | None,
) -> Decimal:
    """Resolve the unit price used by valuation and reconciliation calculations."""
    valuation_price_local = _as_decimal(market_price)
    normalized_product_type = (product_type or "").strip().upper()
    quantity_amount = _as_decimal(quantity)
    if normalized_product_type == "BOND" and not quantity_amount.is_zero():
        local_cost_basis = _as_decimal(cost_basis_local)
        average_cost_local = abs(local_cost_basis / quantity_amount)
        absolute_price_local = abs(valuation_price_local)
        if (
            absolute_price_local > Decimal("0")
            and absolute_price_local < Decimal("200")
            and average_cost_local >= Decimal("500")
        ):
            price_ratio = average_cost_local / absolute_price_local
            if price_ratio >= Decimal("50"):
                valuation_price_local *= Decimal("100")
            elif price_ratio >= Decimal("5"):
                valuation_price_local *= Decimal("10")
    return valuation_price_local
