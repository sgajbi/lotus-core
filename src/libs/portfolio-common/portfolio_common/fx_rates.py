from decimal import Decimal, InvalidOperation


def coerce_positive_fx_rate_or_none(rate: object) -> Decimal | None:
    """Return a positive Decimal FX rate, or None for missing/invalid rates."""
    if rate is None:
        return None
    if isinstance(rate, Decimal):
        normalized_rate = rate
    else:
        try:
            normalized_rate = Decimal(str(rate))
        except (InvalidOperation, ValueError):
            return None
    if normalized_rate <= Decimal("0"):
        return None
    return normalized_rate
