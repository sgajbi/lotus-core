def normalize_transaction_control_code(value: str | None) -> str:
    return str(value or "").strip().upper()
