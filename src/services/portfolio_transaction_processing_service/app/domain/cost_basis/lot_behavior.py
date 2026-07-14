"""Classify transaction types by their canonical cost-basis lot behavior."""

from portfolio_common.domain.transaction.type_registry import get_transaction_type_definition

LOT_OPENING_BEHAVIORS = frozenset(
    {
        "basis_allocation_in",
        "open_lot",
        "open_rights_lot",
        "preserve_or_restate_lot",
        "transfer_basis_in",
    }
)
LOT_STATE_MUTATING_BEHAVIORS = LOT_OPENING_BEHAVIORS | {
    "consume_lot",
    "consume_rights_lot",
    "partial_basis_transfer",
    "preserve_or_consume_lot",
    "transfer_basis_out",
}
STATE_DEPENDENT_LOT_BEHAVIORS = LOT_STATE_MUTATING_BEHAVIORS - LOT_OPENING_BEHAVIORS
INCREMENTAL_SAFE_LOT_BEHAVIORS = LOT_OPENING_BEHAVIORS | STATE_DEPENDENT_LOT_BEHAVIORS | {"none"}
AVERAGE_COST_POOL_LOT_BEHAVIORS = frozenset({"open_lot", "consume_lot"})


def transaction_lot_behavior(transaction_type: object) -> str:
    """Return the governed lot behavior or ``unknown`` for an unsupported type."""

    transaction_type_code = str(transaction_type or "").strip().upper()
    definition = get_transaction_type_definition(transaction_type_code)
    return definition.lot_behavior if definition is not None else "unknown"
