from typing import cast

from portfolio_common.events import TransactionEvent

from .control_code_normalization import normalize_transaction_control_code
from .fx_models import FX_BUSINESS_TRANSACTION_TYPES

FX_DEFAULT_POLICY_ID = "FX_DEFAULT_POLICY"
FX_DEFAULT_POLICY_VERSION = "1.0.0"
FX_CONTRACT_COMPONENT_TYPES = {"FX_CONTRACT_OPEN", "FX_CONTRACT_CLOSE"}


def enrich_fx_transaction_metadata(event: TransactionEvent) -> TransactionEvent:
    """
    Ensures FX events carry deterministic linkage and policy metadata.
    Existing upstream-provided values are preserved.
    """
    transaction_type = normalize_transaction_control_code(event.transaction_type)
    if transaction_type not in FX_BUSINESS_TRANSACTION_TYPES:
        return event

    component_type = normalize_transaction_control_code(event.component_type)
    economic_event_id, linked_transaction_group_id = _resolve_event_linkage_ids(event)
    swap_event_id, near_leg_group_id, far_leg_group_id = _resolve_swap_group_ids(
        event=event,
        transaction_type=transaction_type,
        linked_transaction_group_id=linked_transaction_group_id,
    )
    fx_contract_id = _resolve_fx_contract_id(
        event=event,
        transaction_type=transaction_type,
        component_type=component_type,
        linked_transaction_group_id=linked_transaction_group_id,
        far_leg_group_id=far_leg_group_id,
    )
    instrument_id, security_id = _resolve_contract_instrument_identifiers(
        event=event,
        component_type=component_type,
        fx_contract_id=fx_contract_id,
    )
    fx_contract_open_transaction_id, fx_contract_close_transaction_id = (
        _resolve_contract_lifecycle_transaction_ids(
            event=event,
            component_type=component_type,
            fx_contract_id=fx_contract_id,
        )
    )

    return event.model_copy(
        update=_build_fx_metadata_update(
            event=event,
            component_type=component_type,
            economic_event_id=economic_event_id,
            linked_transaction_group_id=linked_transaction_group_id,
            fx_contract_id=fx_contract_id,
            swap_event_id=swap_event_id,
            near_leg_group_id=near_leg_group_id,
            far_leg_group_id=far_leg_group_id,
            instrument_id=instrument_id,
            security_id=security_id,
            fx_contract_open_transaction_id=fx_contract_open_transaction_id,
            fx_contract_close_transaction_id=fx_contract_close_transaction_id,
        )
    )


def _resolve_event_linkage_ids(event: TransactionEvent) -> tuple[str, str]:
    economic_event_id = (
        event.economic_event_id or f"EVT-FX-{event.portfolio_id}-{event.transaction_id}"
    )
    linked_transaction_group_id = (
        event.linked_transaction_group_id or f"LTG-FX-{event.portfolio_id}-{event.transaction_id}"
    )
    return economic_event_id, linked_transaction_group_id


def _resolve_swap_group_ids(
    *,
    event: TransactionEvent,
    transaction_type: str,
    linked_transaction_group_id: str,
) -> tuple[str | None, str | None, str | None]:
    swap_event_id = event.swap_event_id
    near_leg_group_id = event.near_leg_group_id
    far_leg_group_id = event.far_leg_group_id
    if transaction_type != "FX_SWAP":
        return swap_event_id, near_leg_group_id, far_leg_group_id

    swap_event_id = swap_event_id or f"FXSWAP-{linked_transaction_group_id}"
    near_leg_group_id = near_leg_group_id or f"{swap_event_id}-NEAR"
    far_leg_group_id = far_leg_group_id or f"{swap_event_id}-FAR"
    return swap_event_id, near_leg_group_id, far_leg_group_id


def _resolve_fx_contract_id(
    *,
    event: TransactionEvent,
    transaction_type: str,
    component_type: str,
    linked_transaction_group_id: str,
    far_leg_group_id: str | None,
) -> str | None:
    if event.fx_contract_id:
        return cast(str, event.fx_contract_id)
    if _requires_swap_contract_id(transaction_type, component_type):
        return f"FXC-{far_leg_group_id}"
    if _requires_forward_contract_id(transaction_type, component_type):
        return f"FXC-{linked_transaction_group_id}"
    return None


def _requires_swap_contract_id(transaction_type: str, component_type: str) -> bool:
    return transaction_type == "FX_SWAP" and component_type.startswith("FX_CONTRACT")


def _requires_forward_contract_id(transaction_type: str, component_type: str) -> bool:
    return transaction_type == "FX_FORWARD" or component_type.startswith("FX_CONTRACT")


def _resolve_fx_cash_leg_role(event: TransactionEvent, component_type: str) -> str | None:
    if event.fx_cash_leg_role:
        return cast(str, event.fx_cash_leg_role)
    if component_type == "FX_CASH_SETTLEMENT_BUY":
        return "BUY"
    if component_type == "FX_CASH_SETTLEMENT_SELL":
        return "SELL"
    return None


def _resolve_contract_instrument_identifiers(
    *,
    event: TransactionEvent,
    component_type: str,
    fx_contract_id: str | None,
) -> tuple[str, str]:
    if component_type not in FX_CONTRACT_COMPONENT_TYPES or not fx_contract_id:
        return event.instrument_id, event.security_id
    return fx_contract_id, fx_contract_id


def _resolve_contract_lifecycle_transaction_ids(
    *,
    event: TransactionEvent,
    component_type: str,
    fx_contract_id: str | None,
) -> tuple[str | None, str | None]:
    open_transaction_id = event.fx_contract_open_transaction_id
    close_transaction_id = event.fx_contract_close_transaction_id
    if component_type not in FX_CONTRACT_COMPONENT_TYPES or not fx_contract_id:
        return open_transaction_id, close_transaction_id
    return (
        _resolve_contract_open_transaction_id(event, component_type, open_transaction_id),
        _resolve_contract_close_transaction_id(event, component_type, close_transaction_id),
    )


def _resolve_contract_open_transaction_id(
    event: TransactionEvent,
    component_type: str,
    open_transaction_id: str | None,
) -> str | None:
    if component_type == "FX_CONTRACT_OPEN":
        return open_transaction_id or event.transaction_id
    return open_transaction_id


def _resolve_contract_close_transaction_id(
    event: TransactionEvent,
    component_type: str,
    close_transaction_id: str | None,
) -> str | None:
    if component_type == "FX_CONTRACT_CLOSE":
        return close_transaction_id or event.transaction_id
    return close_transaction_id


def _build_fx_metadata_update(
    *,
    event: TransactionEvent,
    component_type: str,
    economic_event_id: str,
    linked_transaction_group_id: str,
    fx_contract_id: str | None,
    swap_event_id: str | None,
    near_leg_group_id: str | None,
    far_leg_group_id: str | None,
    instrument_id: str,
    security_id: str,
    fx_contract_open_transaction_id: str | None,
    fx_contract_close_transaction_id: str | None,
) -> dict[str, object]:
    update: dict[str, object] = {}
    update.update(_build_core_linkage_update(event, economic_event_id, linked_transaction_group_id))
    update.update(
        _build_contract_linkage_update(
            fx_contract_id=fx_contract_id,
            swap_event_id=swap_event_id,
            near_leg_group_id=near_leg_group_id,
            far_leg_group_id=far_leg_group_id,
            fx_cash_leg_role=_resolve_fx_cash_leg_role(event, component_type),
        )
    )
    update.update(
        _build_instrument_lifecycle_update(
            instrument_id=instrument_id,
            security_id=security_id,
            fx_contract_open_transaction_id=fx_contract_open_transaction_id,
            fx_contract_close_transaction_id=fx_contract_close_transaction_id,
        )
    )
    update.update(_build_fx_processing_mode_update(event))
    return update


def _build_core_linkage_update(
    event: TransactionEvent,
    economic_event_id: str,
    linked_transaction_group_id: str,
) -> dict[str, object]:
    return {
        "economic_event_id": economic_event_id,
        "linked_transaction_group_id": linked_transaction_group_id,
        "calculation_policy_id": event.calculation_policy_id or FX_DEFAULT_POLICY_ID,
        "calculation_policy_version": (
            event.calculation_policy_version or FX_DEFAULT_POLICY_VERSION
        ),
        "component_id": event.component_id or event.transaction_id,
    }


def _build_contract_linkage_update(
    *,
    fx_contract_id: str | None,
    swap_event_id: str | None,
    near_leg_group_id: str | None,
    far_leg_group_id: str | None,
    fx_cash_leg_role: str | None,
) -> dict[str, object]:
    return {
        "fx_contract_id": fx_contract_id,
        "swap_event_id": swap_event_id,
        "near_leg_group_id": near_leg_group_id,
        "far_leg_group_id": far_leg_group_id,
        "fx_cash_leg_role": fx_cash_leg_role,
    }


def _build_instrument_lifecycle_update(
    *,
    instrument_id: str,
    security_id: str,
    fx_contract_open_transaction_id: str | None,
    fx_contract_close_transaction_id: str | None,
) -> dict[str, object]:
    return {
        "instrument_id": instrument_id,
        "security_id": security_id,
        "fx_contract_open_transaction_id": fx_contract_open_transaction_id,
        "fx_contract_close_transaction_id": fx_contract_close_transaction_id,
    }


def _build_fx_processing_mode_update(event: TransactionEvent) -> dict[str, object]:
    return {
        "spot_exposure_model": normalize_transaction_control_code(
            event.spot_exposure_model or "NONE"
        ),
        "fx_realized_pnl_mode": normalize_transaction_control_code(
            event.fx_realized_pnl_mode or "NONE"
        ),
    }
