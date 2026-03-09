from portfolio_common.events import TransactionEvent

FX_DEFAULT_POLICY_ID = "FX_DEFAULT_POLICY"
FX_DEFAULT_POLICY_VERSION = "1.0.0"


def enrich_fx_transaction_metadata(event: TransactionEvent) -> TransactionEvent:
    """
    Ensures FX events carry deterministic linkage and policy metadata.
    Existing upstream-provided values are preserved.
    """
    if event.transaction_type.upper() not in {"FX_SPOT", "FX_FORWARD", "FX_SWAP"}:
        return event

    economic_event_id = (
        event.economic_event_id or f"EVT-FX-{event.portfolio_id}-{event.transaction_id}"
    )
    linked_transaction_group_id = (
        event.linked_transaction_group_id or f"LTG-FX-{event.portfolio_id}-{event.transaction_id}"
    )
    calculation_policy_id = event.calculation_policy_id or FX_DEFAULT_POLICY_ID
    calculation_policy_version = event.calculation_policy_version or FX_DEFAULT_POLICY_VERSION
    component_id = event.component_id or event.transaction_id
    swap_event_id = event.swap_event_id
    near_leg_group_id = event.near_leg_group_id
    far_leg_group_id = event.far_leg_group_id

    if not swap_event_id and event.transaction_type.upper() == "FX_SWAP":
        swap_event_id = f"FXSWAP-{linked_transaction_group_id}"

    if event.transaction_type.upper() == "FX_SWAP":
        near_leg_group_id = near_leg_group_id or f"{swap_event_id}-NEAR"
        far_leg_group_id = far_leg_group_id or f"{swap_event_id}-FAR"

    fx_contract_id = event.fx_contract_id
    component_type = (event.component_type or "").upper()
    if (
        not fx_contract_id
        and event.transaction_type.upper() == "FX_SWAP"
        and component_type.startswith("FX_CONTRACT")
    ):
        fx_contract_id = f"FXC-{far_leg_group_id}"
    elif not fx_contract_id and (
        event.transaction_type.upper() == "FX_FORWARD" or component_type.startswith("FX_CONTRACT")
    ):
        fx_contract_id = f"FXC-{linked_transaction_group_id}"

    fx_cash_leg_role = event.fx_cash_leg_role
    if not fx_cash_leg_role and component_type == "FX_CASH_SETTLEMENT_BUY":
        fx_cash_leg_role = "BUY"
    elif not fx_cash_leg_role and component_type == "FX_CASH_SETTLEMENT_SELL":
        fx_cash_leg_role = "SELL"

    instrument_id = event.instrument_id
    security_id = event.security_id
    fx_contract_open_transaction_id = event.fx_contract_open_transaction_id
    fx_contract_close_transaction_id = event.fx_contract_close_transaction_id
    if component_type in {"FX_CONTRACT_OPEN", "FX_CONTRACT_CLOSE"} and fx_contract_id:
        instrument_id = fx_contract_id
        security_id = fx_contract_id
        if component_type == "FX_CONTRACT_OPEN" and not fx_contract_open_transaction_id:
            fx_contract_open_transaction_id = event.transaction_id
        if component_type == "FX_CONTRACT_CLOSE" and not fx_contract_close_transaction_id:
            fx_contract_close_transaction_id = event.transaction_id

    return event.model_copy(
        update={
            "economic_event_id": economic_event_id,
            "linked_transaction_group_id": linked_transaction_group_id,
            "calculation_policy_id": calculation_policy_id,
            "calculation_policy_version": calculation_policy_version,
            "component_id": component_id,
            "fx_contract_id": fx_contract_id,
            "swap_event_id": swap_event_id,
            "near_leg_group_id": near_leg_group_id,
            "far_leg_group_id": far_leg_group_id,
            "fx_cash_leg_role": fx_cash_leg_role,
            "instrument_id": instrument_id,
            "security_id": security_id,
            "fx_contract_open_transaction_id": fx_contract_open_transaction_id,
            "fx_contract_close_transaction_id": fx_contract_close_transaction_id,
            "spot_exposure_model": event.spot_exposure_model or "NONE",
            "fx_realized_pnl_mode": event.fx_realized_pnl_mode or "NONE",
        }
    )
