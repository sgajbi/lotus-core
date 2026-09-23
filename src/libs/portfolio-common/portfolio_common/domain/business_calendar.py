"""Canonical business-calendar identity."""


def normalize_business_calendar_code(value: object) -> str:
    """Return one stable identifier for ingestion, partitioning, and persistence."""

    if not isinstance(value, str):
        raise ValueError("Business calendar code must be text.")
    normalized = value.strip().upper()
    if not normalized:
        raise ValueError("Business calendar code must not be blank.")
    return normalized
