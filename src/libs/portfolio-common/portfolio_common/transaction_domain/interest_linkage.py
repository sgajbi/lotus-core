from portfolio_common.events import TransactionEvent

from .cash_entry_mode import normalize_cash_entry_mode
from .control_code_normalization import normalize_transaction_control_code

INTEREST_DEFAULT_POLICY_ID = "INTEREST_DEFAULT_POLICY"
INTEREST_DEFAULT_POLICY_VERSION = "1.0.0"


def enrich_interest_transaction_metadata(event: TransactionEvent) -> TransactionEvent:
    """
    Ensures INTEREST events carry deterministic linkage and policy metadata.
    Existing upstream-provided values are preserved.
    """
    if not _is_interest_transaction(event):
        return event

    economic_event_id, linked_transaction_group_id = _resolve_interest_linkage_ids(event)
    calculation_policy_id, calculation_policy_version = _resolve_interest_policy_ids(event)
    cash_entry_mode = normalize_cash_entry_mode(event.cash_entry_mode)
    return event.model_copy(
        update=_build_interest_metadata_update(
            economic_event_id=economic_event_id,
            linked_transaction_group_id=linked_transaction_group_id,
            calculation_policy_id=calculation_policy_id,
            calculation_policy_version=calculation_policy_version,
            cash_entry_mode=cash_entry_mode,
        )
    )


def _is_interest_transaction(event: TransactionEvent) -> bool:
    return normalize_transaction_control_code(event.transaction_type) == "INTEREST"


def _resolve_interest_linkage_ids(event: TransactionEvent) -> tuple[str, str]:
    economic_event_id = (
        event.economic_event_id or f"EVT-INTEREST-{event.portfolio_id}-{event.transaction_id}"
    )
    linked_transaction_group_id = (
        event.linked_transaction_group_id
        or f"LTG-INTEREST-{event.portfolio_id}-{event.transaction_id}"
    )
    return economic_event_id, linked_transaction_group_id


def _resolve_interest_policy_ids(event: TransactionEvent) -> tuple[str, str]:
    calculation_policy_id = event.calculation_policy_id or INTEREST_DEFAULT_POLICY_ID
    calculation_policy_version = event.calculation_policy_version or INTEREST_DEFAULT_POLICY_VERSION
    return calculation_policy_id, calculation_policy_version


def _build_interest_metadata_update(
    *,
    economic_event_id: str,
    linked_transaction_group_id: str,
    calculation_policy_id: str,
    calculation_policy_version: str,
    cash_entry_mode: str,
) -> dict[str, object]:
    return {
        "economic_event_id": economic_event_id,
        "linked_transaction_group_id": linked_transaction_group_id,
        "calculation_policy_id": calculation_policy_id,
        "calculation_policy_version": calculation_policy_version,
        "cash_entry_mode": cash_entry_mode,
    }
