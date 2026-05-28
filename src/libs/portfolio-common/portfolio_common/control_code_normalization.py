def normalize_transaction_control_code(value: str | None) -> str:
    return str(value or "").strip().upper()


def normalize_optional_transaction_control_code(value: str | None) -> str | None:
    if value is None:
        return None
    return normalize_transaction_control_code(value)
