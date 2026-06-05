from portfolio_common.events import TransactionEvent

from .control_code_normalization import normalize_transaction_control_code

BUY_DEFAULT_POLICY_ID = "BUY_DEFAULT_POLICY"
BUY_DEFAULT_POLICY_VERSION = "1.0.0"


def enrich_buy_transaction_metadata(event: TransactionEvent) -> TransactionEvent:
    """
    Ensures BUY events carry deterministic linkage and policy metadata.
    Existing upstream-provided values are preserved.
    """
    if not _is_buy_transaction(event):
        return event

    economic_event_id, linked_transaction_group_id = _resolve_buy_linkage_ids(event)
    calculation_policy_id, calculation_policy_version = _resolve_buy_policy_ids(event)
    return event.model_copy(
        update=_build_buy_metadata_update(
            economic_event_id=economic_event_id,
            linked_transaction_group_id=linked_transaction_group_id,
            calculation_policy_id=calculation_policy_id,
            calculation_policy_version=calculation_policy_version,
        )
    )


def _is_buy_transaction(event: TransactionEvent) -> bool:
    return normalize_transaction_control_code(event.transaction_type) == "BUY"


def _resolve_buy_linkage_ids(event: TransactionEvent) -> tuple[str, str]:
    economic_event_id = (
        event.economic_event_id or f"EVT-BUY-{event.portfolio_id}-{event.transaction_id}"
    )
    linked_transaction_group_id = (
        event.linked_transaction_group_id or f"LTG-BUY-{event.portfolio_id}-{event.transaction_id}"
    )
    return economic_event_id, linked_transaction_group_id


def _resolve_buy_policy_ids(event: TransactionEvent) -> tuple[str, str]:
    calculation_policy_id = event.calculation_policy_id or BUY_DEFAULT_POLICY_ID
    calculation_policy_version = event.calculation_policy_version or BUY_DEFAULT_POLICY_VERSION
    return calculation_policy_id, calculation_policy_version


def _build_buy_metadata_update(
    *,
    economic_event_id: str,
    linked_transaction_group_id: str,
    calculation_policy_id: str,
    calculation_policy_version: str,
) -> dict[str, object]:
    return {
        "economic_event_id": economic_event_id,
        "linked_transaction_group_id": linked_transaction_group_id,
        "calculation_policy_id": calculation_policy_id,
        "calculation_policy_version": calculation_policy_version,
    }
