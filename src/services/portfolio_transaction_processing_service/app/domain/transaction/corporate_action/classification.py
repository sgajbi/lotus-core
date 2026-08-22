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
FRACTIONAL_CASH_BASIS_TRANSACTION_TYPES = frozenset({"CASH_IN_LIEU"})
RECONCILABLE_CORPORATE_ACTION_TYPES = frozenset(BASIS_TRANSFER_CORPORATE_ACTION_TYPES).union(
    SOURCE_QUANTITY_TRANSFER_TRANSACTION_TYPES,
    TARGET_QUANTITY_TRANSFER_TRANSACTION_TYPES,
    FRACTIONAL_CASH_BASIS_TRANSACTION_TYPES,
    {"ADJUSTMENT"},
)
# Child parking is deliberately opt-in. These are the transaction families that the
# parent-manifest policy can govern; identity fields are checked separately so an
# ordinary fee, tax, or adjustment cannot be captured merely by its transaction type.
MANIFEST_GOVERNED_CORPORATE_ACTION_TYPES = RECONCILABLE_CORPORATE_ACTION_TYPES.union({"FEE", "TAX"})
CORPORATE_ACTION_RECONCILIATION_INPUT_TYPES = RECONCILABLE_CORPORATE_ACTION_TYPES
SOURCE_BASIS_TRANSFER_TRANSACTION_TYPES = {"SPIN_OFF", "DEMERGER_OUT"}
TARGET_BASIS_TRANSFER_TRANSACTION_TYPES = {"SPIN_IN", "DEMERGER_IN"}
CASH_CONSIDERATION_TRANSACTION_TYPE = "CASH_CONSIDERATION"
SAME_INSTRUMENT_CORPORATE_ACTION_TYPES = frozenset(
    {
        "SPLIT",
        "REVERSE_SPLIT",
        "CONSOLIDATION",
        "BONUS_ISSUE",
        "STOCK_DIVIDEND",
    }
)


def normalize_corporate_action_transaction_type(transaction_type: str | None) -> str:
    """Return one normalized corporate-action transaction code."""

    return str(transaction_type or "").strip().upper()


def is_reconcilable_corporate_action(transaction_type: str | None) -> bool:
    """Return whether a transaction participates in linked-group reconciliation."""

    return (
        normalize_corporate_action_transaction_type(transaction_type)
        in RECONCILABLE_CORPORATE_ACTION_TYPES
    )


def is_manifest_governed_corporate_action(transaction_type: str | None) -> bool:
    """Return whether a fully identified child may enter manifest-governed parking."""

    return (
        normalize_corporate_action_transaction_type(transaction_type)
        in MANIFEST_GOVERNED_CORPORATE_ACTION_TYPES
    )
