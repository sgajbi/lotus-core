from decimal import Decimal

from portfolio_common.decimal_amounts import decimal_or_none


def coerce_positive_fx_rate_or_none(rate: object) -> Decimal | None:
    """Return a positive Decimal FX rate, or None for missing/invalid rates."""
    normalized_rate = decimal_or_none(rate)
    if normalized_rate is None:
        return None
    if normalized_rate <= Decimal("0"):
        return None
    return normalized_rate
