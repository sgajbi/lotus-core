"""Order linked corporate-action and rights lifecycle transaction legs."""

from typing import Protocol

from .classification import (
    CASH_CONSIDERATION_TRANSACTION_TYPE,
    SOURCE_BASIS_TRANSFER_TRANSACTION_TYPES,
    TARGET_BASIS_TRANSFER_TRANSACTION_TYPES,
    normalize_corporate_action_transaction_type,
)


class CorporateActionOrderable(Protocol):
    """Expose the fields required for deterministic linked-leg ordering."""

    transaction_type: str
    child_sequence_hint: int | None
    target_instrument_id: str | None


_SOURCE_OUT_RANK_TYPES = SOURCE_BASIS_TRANSFER_TRANSACTION_TYPES | {
    "RIGHTS_ANNOUNCE",
    "RIGHTS_ALLOCATE",
}
_TARGET_IN_RANK_TYPES = TARGET_BASIS_TRANSFER_TRANSACTION_TYPES | {
    "RIGHTS_SUBSCRIBE",
    "RIGHTS_OVERSUBSCRIBE",
    "RIGHTS_SELL",
    "RIGHTS_EXPIRE",
    "RIGHTS_ADJUSTMENT",
}
_CASH_CONSIDERATION_RANK_TYPES = {
    CASH_CONSIDERATION_TRANSACTION_TYPE,
    "RIGHTS_SHARE_DELIVERY",
}
_DEPENDENCY_RANK_BY_TYPE = {
    **dict.fromkeys(_SOURCE_OUT_RANK_TYPES, 0),
    **dict.fromkeys(_TARGET_IN_RANK_TYPES, 1),
    **dict.fromkeys(_CASH_CONSIDERATION_RANK_TYPES, 2),
    "RIGHTS_REFUND": 3,
}


def corporate_action_dependency_rank(transaction: CorporateActionOrderable) -> int:
    """Return the deterministic dependency rank for linked lifecycle legs.

    Lower ranks are processed first:
    0: source-out legs / rights announce-allocate stages
    1: target-in legs / rights election legs
    2: cash consideration marker legs / rights delivery legs
    3: rights refund stage
    4: non-Bundle-A / unknown
    """
    transaction_type = normalize_corporate_action_transaction_type(transaction.transaction_type)
    return _DEPENDENCY_RANK_BY_TYPE.get(transaction_type, 4)


def corporate_action_target_order_key(
    transaction: CorporateActionOrderable,
) -> tuple[int, str]:
    """Return deterministic sequence and instrument ordering for target legs.

    Priority:
    1) child_sequence_hint (when present, otherwise very large sentinel)
    2) target_instrument_id (lexicographic fallback)
    """
    child_sequence_hint = transaction.child_sequence_hint
    target_instrument_id = str(transaction.target_instrument_id or "")
    sequence = int(child_sequence_hint) if child_sequence_hint is not None else 2_147_483_647
    return (sequence, target_instrument_id)
