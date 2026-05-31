from decimal import Decimal

from portfolio_common.decimal_amounts import decimal_or_none


def coerce_positive_market_price_or_none(price: object) -> Decimal | None:
    """Return a positive Decimal market price, or None for missing/invalid prices."""
    normalized_price = decimal_or_none(price)
    if normalized_price is None:
        return None
    if normalized_price <= Decimal("0"):
        return None
    return normalized_price
