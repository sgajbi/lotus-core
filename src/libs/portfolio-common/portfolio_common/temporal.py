"""Shared policies for governed financial timestamps."""

from datetime import UTC, datetime


def standardize_governed_datetime(value: object) -> object:
    """Reject ambiguous datetimes and canonicalize timezone-aware values to UTC."""
    if value is None:
        return value
    if not isinstance(value, (str, datetime)):
        raise ValueError("Governed datetime must be a timezone-aware ISO-8601 string or datetime.")
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Governed datetime must be timezone-aware.")
    return value.astimezone(UTC)
