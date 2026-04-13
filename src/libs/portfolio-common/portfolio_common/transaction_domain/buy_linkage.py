from portfolio_common.events import TransactionEvent

BUY_DEFAULT_POLICY_ID = "BUY_DEFAULT_POLICY"
BUY_DEFAULT_POLICY_VERSION = "1.0.0"


def enrich_buy_transaction_metadata(event: TransactionEvent) -> TransactionEvent:
    """
    Ensures BUY events carry deterministic linkage and policy metadata.
    Existing upstream-provided values are preserved.
    """
    if event.transaction_type.upper() != "BUY":
        return event

    economic_event_id = event.economic_event_id or f"EVT-BUY-{event.portfolio_id}-{event.transaction_id}"
    linked_transaction_group_id = (
        event.linked_transaction_group_id or f"LTG-BUY-{event.portfolio_id}-{event.transaction_id}"
    )
    calculation_policy_id = event.calculation_policy_id or BUY_DEFAULT_POLICY_ID
    calculation_policy_version = (
        event.calculation_policy_version or BUY_DEFAULT_POLICY_VERSION
    )

    return event.model_copy(
        update={
            "economic_event_id": economic_event_id,
            "linked_transaction_group_id": linked_transaction_group_id,
            "calculation_policy_id": calculation_policy_id,
            "calculation_policy_version": calculation_policy_version,
        }
    )
