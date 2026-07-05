from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Callable

from portfolio_common.decimal_amounts import required_decimal
from portfolio_common.transaction_domain.control_code_normalization import (
    normalize_transaction_control_code,
)

CASH_POSITION_INFLOW_TRANSACTION_TYPES = {"DEPOSIT"}
CASH_POSITION_OUTFLOW_TRANSACTION_TYPES = {"WITHDRAWAL", "FEE", "TAX"}
CASH_POSITION_DELTA_TRANSACTION_TYPES = (
    CASH_POSITION_INFLOW_TRANSACTION_TYPES
    | CASH_POSITION_OUTFLOW_TRANSACTION_TYPES
    | {"ADJUSTMENT", "FX_CASH_SETTLEMENT_BUY", "FX_CASH_SETTLEMENT_SELL"}
)
POSITION_TRANSFER_TRANSACTION_TYPES = {
    "TRANSFER_IN",
    "TRANSFER_OUT",
    "MERGER_IN",
    "MERGER_OUT",
    "EXCHANGE_IN",
    "EXCHANGE_OUT",
    "REPLACEMENT_IN",
    "REPLACEMENT_OUT",
    "SPIN_IN",
    "DEMERGER_IN",
    "RIGHTS_ALLOCATE",
    "RIGHTS_SHARE_DELIVERY",
    "RIGHTS_SUBSCRIBE",
    "RIGHTS_OVERSUBSCRIBE",
    "RIGHTS_SELL",
    "RIGHTS_EXPIRE",
}
POSITION_TRANSFER_INFLOW_TRANSACTION_TYPES = {
    "TRANSFER_IN",
    "MERGER_IN",
    "EXCHANGE_IN",
    "REPLACEMENT_IN",
    "SPIN_IN",
    "DEMERGER_IN",
    "RIGHTS_ALLOCATE",
    "RIGHTS_SHARE_DELIVERY",
}
SAME_INSTRUMENT_CORPORATE_ACTION_TYPES = {
    "SPLIT",
    "REVERSE_SPLIT",
    "CONSOLIDATION",
    "BONUS_ISSUE",
    "STOCK_DIVIDEND",
}
SAME_INSTRUMENT_QUANTITY_DECREASE_TYPES = {"REVERSE_SPLIT", "CONSOLIDATION"}
FX_COMPONENT_PROCESSING_TYPES = {
    "FX_CONTRACT_OPEN",
    "FX_CONTRACT_CLOSE",
    "FX_CASH_SETTLEMENT_BUY",
    "FX_CASH_SETTLEMENT_SELL",
}
_POSITION_START_DATE = date(1970, 1, 1)


@dataclass(frozen=True, slots=True)
class PositionBalanceState:
    quantity: Decimal = Decimal(0)
    cost_basis: Decimal = Decimal(0)
    cost_basis_local: Decimal = Decimal(0)


@dataclass(frozen=True, slots=True)
class BackdatedReplayDecision:
    should_queue_replay: bool
    effective_completed_date: date
    replay_watermark_date: date | None
    reason: str


_PositionUpdateHandler = Callable[[PositionBalanceState, Any, str], PositionBalanceState]


def plan_backdated_replay(
    *,
    event_epoch: int | None,
    transaction_date: date,
    current_watermark_date: date,
    latest_position_history_date: date | None,
    latest_completed_snapshot_date: date | None,
) -> BackdatedReplayDecision:
    effective_completed_date = max(
        current_watermark_date,
        latest_position_history_date if latest_position_history_date else _POSITION_START_DATE,
        latest_completed_snapshot_date if latest_completed_snapshot_date else _POSITION_START_DATE,
    )
    should_queue_replay = event_epoch is None and transaction_date < effective_completed_date
    return BackdatedReplayDecision(
        should_queue_replay=should_queue_replay,
        effective_completed_date=effective_completed_date,
        replay_watermark_date=transaction_date - timedelta(days=1) if should_queue_replay else None,
        reason="original_backdated_transaction"
        if should_queue_replay
        else "current_or_replay_event",
    )


def calculate_next_position_state(
    current_state: PositionBalanceState,
    transaction: Any,
) -> PositionBalanceState:
    txn_type = _resolve_effective_processing_transaction_type(transaction)
    handler = _position_update_handler(txn_type)
    next_state = (
        handler(current_state, transaction, txn_type) if handler is not None else current_state
    )
    return _zeroed_cost_basis_when_flat(next_state)


def normalize_position_code(value: object) -> str:
    return str(value or "").strip().upper()


def _resolve_effective_processing_transaction_type(transaction: Any) -> str:
    component_type = normalize_transaction_control_code(
        getattr(transaction, "component_type", None)
    )
    if component_type in FX_COMPONENT_PROCESSING_TYPES:
        return component_type
    return normalize_transaction_control_code(getattr(transaction, "transaction_type", None))


def cash_position_deltas(transaction: Any, txn_type: str) -> tuple[Decimal, Decimal, Decimal]:
    quantity_delta = _cash_position_amount_delta(transaction, txn_type)
    use_quantity_fallback = txn_type == "ADJUSTMENT" or txn_type in (
        CASH_POSITION_INFLOW_TRANSACTION_TYPES | CASH_POSITION_OUTFLOW_TRANSACTION_TYPES
    )
    net_cost = _optional_decimal(
        transaction.net_cost,
        field_name="net_cost",
    )
    net_cost_local = _optional_decimal(
        transaction.net_cost_local,
        field_name="net_cost_local",
    )
    cost_basis_delta = (
        net_cost
        if net_cost is not None and not (use_quantity_fallback and net_cost == Decimal(0))
        else quantity_delta
    )
    cost_basis_local_delta = (
        net_cost_local
        if net_cost_local is not None
        and not (use_quantity_fallback and net_cost_local == Decimal(0))
        else quantity_delta
    )
    return quantity_delta, cost_basis_delta, cost_basis_local_delta


def _position_update_handler(txn_type: str) -> _PositionUpdateHandler | None:
    if txn_type == "BUY":
        return _buy_position_state

    if txn_type in {"SELL", "CASH_IN_LIEU"}:
        return _sell_position_state

    if txn_type in CASH_POSITION_DELTA_TRANSACTION_TYPES:
        return _cash_delta_position_state

    if txn_type in POSITION_TRANSFER_TRANSACTION_TYPES:
        return _transfer_position_state

    if txn_type in SAME_INSTRUMENT_CORPORATE_ACTION_TYPES:
        return _same_instrument_action_state

    if txn_type in {"SPIN_OFF", "DEMERGER_OUT"}:
        return _spin_off_position_state

    if txn_type == "FX_CONTRACT_OPEN":
        return _fx_contract_open_position_state

    if txn_type == "FX_CONTRACT_CLOSE":
        return _fx_contract_close_position_state

    return None


def _position_state(
    quantity: Decimal, cost_basis: Decimal, cost_basis_local: Decimal
) -> PositionBalanceState:
    return PositionBalanceState(
        quantity=quantity,
        cost_basis=cost_basis,
        cost_basis_local=cost_basis_local,
    )


def _buy_position_state(
    current_state: PositionBalanceState, transaction: Any, _txn_type: str
) -> PositionBalanceState:
    return _position_state(
        quantity=current_state.quantity + transaction.quantity,
        cost_basis=_cost_basis_with_optional_net_cost(
            current_state.cost_basis, transaction.net_cost
        ),
        cost_basis_local=_cost_basis_with_optional_net_cost(
            current_state.cost_basis_local, transaction.net_cost_local
        ),
    )


def _sell_position_state(
    current_state: PositionBalanceState, transaction: Any, _txn_type: str
) -> PositionBalanceState:
    return _position_state(
        quantity=current_state.quantity - transaction.quantity,
        cost_basis=_cost_basis_with_optional_net_cost(
            current_state.cost_basis, transaction.net_cost
        ),
        cost_basis_local=_cost_basis_with_optional_net_cost(
            current_state.cost_basis_local, transaction.net_cost_local
        ),
    )


def _cost_basis_with_optional_net_cost(
    current_cost_basis: Decimal, net_cost: Decimal | None
) -> Decimal:
    return current_cost_basis + net_cost if net_cost is not None else current_cost_basis


def _cash_delta_position_state(
    current_state: PositionBalanceState, transaction: Any, txn_type: str
) -> PositionBalanceState:
    quantity_delta, cost_basis_delta, cost_basis_local_delta = cash_position_deltas(
        transaction, txn_type
    )
    return _position_state(
        quantity=current_state.quantity + quantity_delta,
        cost_basis=current_state.cost_basis + cost_basis_delta,
        cost_basis_local=current_state.cost_basis_local + cost_basis_local_delta,
    )


def _transfer_position_state(
    current_state: PositionBalanceState, transaction: Any, txn_type: str
) -> PositionBalanceState:
    transfer_quantity = transaction.quantity
    if transfer_quantity <= Decimal(0):
        return current_state

    is_inflow = txn_type in POSITION_TRANSFER_INFLOW_TRANSACTION_TYPES
    transfer_sign = Decimal(1) if is_inflow else Decimal(-1)
    return _position_state(
        quantity=current_state.quantity + (transfer_sign * transfer_quantity),
        cost_basis=_transfer_cost_basis(
            current_state.cost_basis,
            transaction.net_cost,
            transaction.gross_transaction_amount,
            is_inflow,
        ),
        cost_basis_local=_transfer_cost_basis(
            current_state.cost_basis_local,
            transaction.net_cost_local,
            transaction.gross_transaction_amount,
            is_inflow,
        ),
    )


def _transfer_cost_basis(
    current_cost_basis: Decimal,
    net_cost: Decimal | None,
    gross_transaction_amount: Decimal,
    is_inflow: bool,
) -> Decimal:
    if net_cost is not None:
        return current_cost_basis + net_cost
    if is_inflow:
        return current_cost_basis + gross_transaction_amount
    return current_cost_basis - gross_transaction_amount


def _same_instrument_action_state(
    current_state: PositionBalanceState, transaction: Any, txn_type: str
) -> PositionBalanceState:
    quantity_delta_sign = (
        Decimal(-1) if txn_type in SAME_INSTRUMENT_QUANTITY_DECREASE_TYPES else Decimal(1)
    )
    return _quantity_delta_position_state(current_state, quantity_delta_sign * transaction.quantity)


def _spin_off_position_state(
    current_state: PositionBalanceState, transaction: Any, _txn_type: str
) -> PositionBalanceState:
    quantity_delta = -transaction.quantity if transaction.quantity > Decimal(0) else Decimal(0)
    return _position_state(
        quantity=current_state.quantity + quantity_delta,
        cost_basis=_spin_off_cost_basis(
            current_state.cost_basis,
            transaction.net_cost,
            transaction.gross_transaction_amount,
        ),
        cost_basis_local=_spin_off_cost_basis(
            current_state.cost_basis_local,
            transaction.net_cost_local,
            transaction.gross_transaction_amount,
        ),
    )


def _spin_off_cost_basis(
    current_cost_basis: Decimal,
    net_cost: Decimal | None,
    gross_transaction_amount: Decimal,
) -> Decimal:
    if net_cost is not None:
        return current_cost_basis + net_cost
    return current_cost_basis - gross_transaction_amount


def _quantity_delta_position_state(
    current_state: PositionBalanceState, quantity_delta: Decimal
) -> PositionBalanceState:
    return _position_state(
        quantity=current_state.quantity + quantity_delta,
        cost_basis=current_state.cost_basis,
        cost_basis_local=current_state.cost_basis_local,
    )


def _fx_contract_open_position_state(
    current_state: PositionBalanceState, _transaction: Any, _txn_type: str
) -> PositionBalanceState:
    return _quantity_delta_position_state(current_state, Decimal(1))


def _fx_contract_close_position_state(
    current_state: PositionBalanceState, _transaction: Any, _txn_type: str
) -> PositionBalanceState:
    return _quantity_delta_position_state(current_state, Decimal(-1))


def _zeroed_cost_basis_when_flat(current_state: PositionBalanceState) -> PositionBalanceState:
    if not current_state.quantity.is_zero():
        return current_state
    return _position_state(
        quantity=current_state.quantity,
        cost_basis=Decimal(0),
        cost_basis_local=Decimal(0),
    )


def _cash_position_amount_delta(transaction: Any, txn_type: str) -> Decimal:
    gross_amount = _decimal_or_zero(
        transaction.gross_transaction_amount,
        field_name="gross_transaction_amount",
    )
    quantity_amount = _decimal_or_zero(
        transaction.quantity,
        field_name="quantity",
    )
    magnitude = abs(gross_amount if not gross_amount.is_zero() else quantity_amount)
    if txn_type == "FEE":
        net_cost_local = _optional_decimal(
            transaction.net_cost_local,
            field_name="net_cost_local",
        )
        if net_cost_local is not None and not net_cost_local.is_zero():
            magnitude = abs(net_cost_local)
    if txn_type in CASH_POSITION_INFLOW_TRANSACTION_TYPES | {
        "ADJUSTMENT",
        "FX_CASH_SETTLEMENT_BUY",
    }:
        if txn_type == "ADJUSTMENT":
            movement_direction = normalize_position_code(transaction.movement_direction or "INFLOW")
            return -magnitude if movement_direction == "OUTFLOW" else magnitude
        return magnitude
    return -magnitude


def _decimal_or_zero(value: object, *, field_name: str) -> Decimal:
    if value is None or (isinstance(value, str) and not value.strip()):
        return Decimal(0)
    return Decimal(required_decimal(value, field_name=field_name))


def _optional_decimal(value: object, *, field_name: str) -> Decimal | None:
    if value is None:
        return None
    return Decimal(required_decimal(value, field_name=field_name))
