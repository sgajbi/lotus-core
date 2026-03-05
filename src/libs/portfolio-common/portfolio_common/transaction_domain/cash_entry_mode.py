AUTO_CASH_ENTRY_MODE = "AUTO"
EXTERNAL_CASH_ENTRY_MODE = "EXTERNAL"

SUPPORTED_CASH_ENTRY_MODES = {
    AUTO_CASH_ENTRY_MODE,
    EXTERNAL_CASH_ENTRY_MODE,
}


def normalize_cash_entry_mode(mode: str | None) -> str:
    normalized = (mode or AUTO_CASH_ENTRY_MODE).upper()
    if normalized not in SUPPORTED_CASH_ENTRY_MODES:
        return AUTO_CASH_ENTRY_MODE
    return normalized


def is_external_cash_entry_mode(mode: str | None) -> bool:
    return normalize_cash_entry_mode(mode) == EXTERNAL_CASH_ENTRY_MODE
