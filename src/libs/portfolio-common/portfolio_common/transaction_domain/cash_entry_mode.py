from .control_code_normalization import normalize_transaction_control_code

AUTO_GENERATE_CASH_ENTRY_MODE = "AUTO_GENERATE"
UPSTREAM_PROVIDED_CASH_ENTRY_MODE = "UPSTREAM_PROVIDED"

SUPPORTED_CASH_ENTRY_MODES = {
    AUTO_GENERATE_CASH_ENTRY_MODE,
    UPSTREAM_PROVIDED_CASH_ENTRY_MODE,
}


def normalize_cash_entry_mode(mode: str | None) -> str:
    normalized = normalize_transaction_control_code(mode or AUTO_GENERATE_CASH_ENTRY_MODE)
    if normalized not in SUPPORTED_CASH_ENTRY_MODES:
        raise ValueError(
            "Unsupported cash_entry_mode. Expected AUTO_GENERATE or " "UPSTREAM_PROVIDED."
        )
    return normalized


def is_upstream_provided_cash_entry_mode(mode: str | None) -> bool:
    return normalize_cash_entry_mode(mode) == UPSTREAM_PROVIDED_CASH_ENTRY_MODE
