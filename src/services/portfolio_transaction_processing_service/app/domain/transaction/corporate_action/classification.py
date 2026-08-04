"""Classify corporate-action basis-transfer transaction legs."""

BASIS_TRANSFER_CORPORATE_ACTION_TYPES = {
    "SPIN_OFF",
    "SPIN_IN",
    "DEMERGER_OUT",
    "DEMERGER_IN",
    "CASH_CONSIDERATION",
}
QUANTITY_TRANSFER_CORPORATE_ACTION_PAIRS = {
    "MERGER_OUT": "MERGER_IN",
    "EXCHANGE_OUT": "EXCHANGE_IN",
    "REPLACEMENT_OUT": "REPLACEMENT_IN",
}
SOURCE_QUANTITY_TRANSFER_TRANSACTION_TYPES = frozenset(QUANTITY_TRANSFER_CORPORATE_ACTION_PAIRS)
TARGET_QUANTITY_TRANSFER_TRANSACTION_TYPES = frozenset(
    QUANTITY_TRANSFER_CORPORATE_ACTION_PAIRS.values()
)
RECONCILABLE_CORPORATE_ACTION_TYPES = frozenset(BASIS_TRANSFER_CORPORATE_ACTION_TYPES).union(
    SOURCE_QUANTITY_TRANSFER_TRANSACTION_TYPES,
    TARGET_QUANTITY_TRANSFER_TRANSACTION_TYPES,
)
SOURCE_BASIS_TRANSFER_TRANSACTION_TYPES = {"SPIN_OFF", "DEMERGER_OUT"}
TARGET_BASIS_TRANSFER_TRANSACTION_TYPES = {"SPIN_IN", "DEMERGER_IN"}
CASH_CONSIDERATION_TRANSACTION_TYPE = "CASH_CONSIDERATION"


def normalize_corporate_action_transaction_type(transaction_type: str | None) -> str:
    """Return one normalized corporate-action transaction code."""

    return str(transaction_type or "").strip().upper()


def is_reconcilable_corporate_action(transaction_type: str | None) -> bool:
    """Return whether a transaction participates in linked-group reconciliation."""

    return (
        normalize_corporate_action_transaction_type(transaction_type)
        in RECONCILABLE_CORPORATE_ACTION_TYPES
    )
