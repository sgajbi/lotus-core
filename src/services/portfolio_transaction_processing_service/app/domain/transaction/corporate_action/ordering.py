from typing import Any

from .ca_bundle_a_constants import (
    CA_BUNDLE_A_CASH_CONSIDERATION_TYPE,
    CA_BUNDLE_A_SOURCE_OUT_TYPES,
    CA_BUNDLE_A_TARGET_IN_TYPES,
    normalize_ca_bundle_a_transaction_type,
)

_SOURCE_OUT_RANK_TYPES = CA_BUNDLE_A_SOURCE_OUT_TYPES | {
    "RIGHTS_ANNOUNCE",
    "RIGHTS_ALLOCATE",
}
_TARGET_IN_RANK_TYPES = CA_BUNDLE_A_TARGET_IN_TYPES | {
    "RIGHTS_SUBSCRIBE",
    "RIGHTS_OVERSUBSCRIBE",
    "RIGHTS_SELL",
    "RIGHTS_EXPIRE",
    "RIGHTS_ADJUSTMENT",
}
_CASH_CONSIDERATION_RANK_TYPES = {
    CA_BUNDLE_A_CASH_CONSIDERATION_TYPE,
    "RIGHTS_SHARE_DELIVERY",
}
_DEPENDENCY_RANK_BY_TYPE = {
    **dict.fromkeys(_SOURCE_OUT_RANK_TYPES, 0),
    **dict.fromkeys(_TARGET_IN_RANK_TYPES, 1),
    **dict.fromkeys(_CASH_CONSIDERATION_RANK_TYPES, 2),
    "RIGHTS_REFUND": 3,
}


def ca_bundle_a_dependency_rank(event: Any) -> int:
    """
    Deterministic dependency rank for Bundle A child legs.

    Lower ranks are processed first:
    0: source-out legs / rights announce-allocate stages
    1: target-in legs / rights election legs
    2: cash consideration marker legs / rights delivery legs
    3: rights refund stage
    4: non-Bundle-A / unknown
    """
    transaction_type = normalize_ca_bundle_a_transaction_type(
        getattr(event, "transaction_type", "")
    )
    return _DEPENDENCY_RANK_BY_TYPE.get(transaction_type, 4)


def ca_bundle_a_target_order_key(event: Any) -> tuple[int, str]:
    """
    Deterministic ordering for multi-target children.
    Priority:
    1) child_sequence_hint (when present, otherwise very large sentinel)
    2) target_instrument_id (lexicographic fallback)
    """
    child_sequence_hint = getattr(event, "child_sequence_hint", None)
    target_instrument_id = str(getattr(event, "target_instrument_id", "") or "")
    sequence = int(child_sequence_hint) if child_sequence_hint is not None else 2_147_483_647
    return (sequence, target_instrument_id)
