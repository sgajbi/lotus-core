from portfolio_common.events import TransactionEvent

SELL_FIFO_POLICY_ID = "SELL_FIFO_POLICY"
SELL_AVCO_POLICY_ID = "SELL_AVCO_POLICY"
SELL_DEFAULT_POLICY_VERSION = "1.0.0"


def enrich_sell_transaction_metadata(
    event: TransactionEvent, *, cost_basis_method: str | None = None
) -> TransactionEvent:
    """
    Ensures SELL events carry deterministic linkage and policy metadata.
    Existing upstream-provided values are preserved.
    """
    if event.transaction_type.upper() != "SELL":
        return event

    economic_event_id = (
        event.economic_event_id or f"EVT-SELL-{event.portfolio_id}-{event.transaction_id}"
    )
    linked_transaction_group_id = (
        event.linked_transaction_group_id or f"LTG-SELL-{event.portfolio_id}-{event.transaction_id}"
    )
    if cost_basis_method == "AVCO":
        resolved_policy_id = SELL_AVCO_POLICY_ID
    else:
        resolved_policy_id = SELL_FIFO_POLICY_ID
    calculation_policy_id = event.calculation_policy_id or resolved_policy_id
    calculation_policy_version = event.calculation_policy_version or SELL_DEFAULT_POLICY_VERSION

    return event.model_copy(
        update={
            "economic_event_id": economic_event_id,
            "linked_transaction_group_id": linked_transaction_group_id,
            "calculation_policy_id": calculation_policy_id,
            "calculation_policy_version": calculation_policy_version,
        }
    )
