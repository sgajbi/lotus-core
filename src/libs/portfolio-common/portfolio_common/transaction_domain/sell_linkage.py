from portfolio_common.cost_basis import CostBasisMethod, normalize_cost_basis_method
from portfolio_common.events import TransactionEvent

from .control_code_normalization import normalize_transaction_control_code

SELL_FIFO_POLICY_ID = "SELL_FIFO_POLICY"
SELL_AVCO_POLICY_ID = "SELL_AVCO_POLICY"
SELL_DEFAULT_POLICY_VERSION = "1.0.0"


def enrich_sell_transaction_metadata(
    event: TransactionEvent, *, cost_basis_method: str | CostBasisMethod | None = None
) -> TransactionEvent:
    """
    Ensures SELL events carry deterministic linkage and policy metadata.
    Existing upstream-provided values are preserved.
    """
    if not _is_sell_transaction(event):
        return event

    economic_event_id, linked_transaction_group_id = _resolve_sell_linkage_ids(event)
    calculation_policy_id, calculation_policy_version = _resolve_sell_policy_ids(
        event, cost_basis_method
    )
    return event.model_copy(
        update=_build_sell_metadata_update(
            economic_event_id=economic_event_id,
            linked_transaction_group_id=linked_transaction_group_id,
            calculation_policy_id=calculation_policy_id,
            calculation_policy_version=calculation_policy_version,
        )
    )


def _is_sell_transaction(event: TransactionEvent) -> bool:
    return normalize_transaction_control_code(event.transaction_type) == "SELL"


def _resolve_sell_linkage_ids(event: TransactionEvent) -> tuple[str, str]:
    economic_event_id = (
        event.economic_event_id or f"EVT-SELL-{event.portfolio_id}-{event.transaction_id}"
    )
    linked_transaction_group_id = (
        event.linked_transaction_group_id or f"LTG-SELL-{event.portfolio_id}-{event.transaction_id}"
    )
    return economic_event_id, linked_transaction_group_id


def _resolve_sell_policy_ids(
    event: TransactionEvent,
    cost_basis_method: str | CostBasisMethod | None,
) -> tuple[str, str]:
    resolved_policy_id = _resolve_cost_basis_policy_id(cost_basis_method)
    calculation_policy_id = event.calculation_policy_id or resolved_policy_id
    calculation_policy_version = event.calculation_policy_version or SELL_DEFAULT_POLICY_VERSION
    return calculation_policy_id, calculation_policy_version


def _resolve_cost_basis_policy_id(cost_basis_method: str | CostBasisMethod | None) -> str:
    resolved_method = normalize_cost_basis_method(cost_basis_method)
    if resolved_method is CostBasisMethod.AVCO:
        return SELL_AVCO_POLICY_ID
    return SELL_FIFO_POLICY_ID


def _build_sell_metadata_update(
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
