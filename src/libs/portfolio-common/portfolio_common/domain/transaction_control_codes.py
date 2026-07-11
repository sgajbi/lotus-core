"""Canonical transaction control-code normalization policy."""


def normalize_transaction_control_code(value: str | None) -> str:
    """Return the canonical uppercase transaction control code."""
    return str(value or "").strip().upper()


def normalize_optional_transaction_control_code(value: str | None) -> str | None:
    """Normalize a transaction control code while preserving a missing value."""
    if value is None:
        return None
    return normalize_transaction_control_code(value)
