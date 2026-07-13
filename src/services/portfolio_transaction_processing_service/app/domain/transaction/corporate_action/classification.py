"""Classify corporate-action basis-transfer transaction legs."""

BASIS_TRANSFER_CORPORATE_ACTION_TYPES = {
    "SPIN_OFF",
    "SPIN_IN",
    "DEMERGER_OUT",
    "DEMERGER_IN",
    "CASH_CONSIDERATION",
}
SOURCE_BASIS_TRANSFER_TRANSACTION_TYPES = {"SPIN_OFF", "DEMERGER_OUT"}
TARGET_BASIS_TRANSFER_TRANSACTION_TYPES = {"SPIN_IN", "DEMERGER_IN"}
CASH_CONSIDERATION_TRANSACTION_TYPE = "CASH_CONSIDERATION"


def normalize_corporate_action_transaction_type(transaction_type: str | None) -> str:
    """Return one normalized corporate-action transaction code."""

    return str(transaction_type or "").strip().upper()
