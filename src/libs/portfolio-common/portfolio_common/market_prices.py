from decimal import Decimal, InvalidOperation


def coerce_positive_market_price_or_none(price: object) -> Decimal | None:
    """Return a positive Decimal market price, or None for missing/invalid prices."""
    if price is None:
        return None
    if isinstance(price, Decimal):
        normalized_price = price
    else:
        try:
            normalized_price = Decimal(str(price))
        except (InvalidOperation, ValueError):
            return None
    if normalized_price <= Decimal("0"):
        return None
    return normalized_price
