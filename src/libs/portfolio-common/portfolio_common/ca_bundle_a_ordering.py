from typing import Any

CA_BUNDLE_A_SOURCE_OUT_TYPES = {"SPIN_OFF", "DEMERGER_OUT"}
CA_BUNDLE_A_TARGET_IN_TYPES = {"SPIN_IN", "DEMERGER_IN"}
CA_BUNDLE_A_CASH_CONSIDERATION_TYPE = "CASH_CONSIDERATION"


def ca_bundle_a_dependency_rank(event: Any) -> int:
    """
    Deterministic dependency rank for Bundle A child legs.

    Lower ranks are processed first:
    0: source-out legs
    1: target-in legs
    2: cash consideration marker legs
    3: non-Bundle-A / unknown
    """
    transaction_type = str(getattr(event, "transaction_type", "") or "").upper()
    if transaction_type in CA_BUNDLE_A_SOURCE_OUT_TYPES:
        return 0
    if transaction_type in CA_BUNDLE_A_TARGET_IN_TYPES:
        return 1
    if transaction_type == CA_BUNDLE_A_CASH_CONSIDERATION_TYPE:
        return 2
    return 3


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
