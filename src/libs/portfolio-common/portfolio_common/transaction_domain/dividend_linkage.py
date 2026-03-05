from portfolio_common.events import TransactionEvent

DIVIDEND_DEFAULT_POLICY_ID = "DIVIDEND_DEFAULT_POLICY"
DIVIDEND_DEFAULT_POLICY_VERSION = "1.0.0"


def enrich_dividend_transaction_metadata(event: TransactionEvent) -> TransactionEvent:
    """
    Ensures DIVIDEND events carry deterministic linkage and policy metadata.
    Existing upstream-provided values are preserved.
    """
    if event.transaction_type.upper() != "DIVIDEND":
        return event

    economic_event_id = (
        event.economic_event_id
        or f"EVT-DIVIDEND-{event.portfolio_id}-{event.transaction_id}"
    )
    linked_transaction_group_id = (
        event.linked_transaction_group_id
        or f"LTG-DIVIDEND-{event.portfolio_id}-{event.transaction_id}"
    )
    calculation_policy_id = event.calculation_policy_id or DIVIDEND_DEFAULT_POLICY_ID
    calculation_policy_version = (
        event.calculation_policy_version or DIVIDEND_DEFAULT_POLICY_VERSION
    )

    return event.model_copy(
        update={
            "economic_event_id": economic_event_id,
            "linked_transaction_group_id": linked_transaction_group_id,
            "calculation_policy_id": calculation_policy_id,
            "calculation_policy_version": calculation_policy_version,
        }
    )
