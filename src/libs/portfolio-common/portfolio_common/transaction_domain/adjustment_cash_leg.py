from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, cast

from portfolio_common.events import TransactionEvent
from portfolio_common.transaction_type_registry import TRANSACTION_TYPE_REGISTRY

from .cash_entry_mode import AUTO_GENERATE_CASH_ENTRY_MODE, normalize_cash_entry_mode
from .control_code_normalization import normalize_transaction_control_code

ADJUSTMENT_TRANSACTION_TYPE = "ADJUSTMENT"

AUTO_GENERATE_ELIGIBLE_TRANSACTION_TYPES = frozenset(
    code
    for code, definition in TRANSACTION_TYPE_REGISTRY.items()
    if definition.production_booking_allowed
    and definition.lifecycle_family in {"trade", "income"}
    and definition.cash_effect in {"inflow", "outflow"}
    and definition.settlement_behavior == "requires_cash_leg"
)

AdjustmentResolver = Callable[[TransactionEvent, Decimal], tuple[Decimal, str, str]]


@dataclass(frozen=True)
class AdjustmentCashLegError(ValueError):
    field: str
    message: str

    def __str__(self) -> str:
        return f"{self.field}: {self.message}"


def should_auto_generate_cash_leg(event: TransactionEvent) -> bool:
    if event.cash_entry_mode is None:
        return False
    mode = normalize_cash_entry_mode(event.cash_entry_mode)
    transaction_type = normalize_transaction_control_code(event.transaction_type)
    return (
        mode == AUTO_GENERATE_CASH_ENTRY_MODE
        and transaction_type in AUTO_GENERATE_ELIGIBLE_TRANSACTION_TYPES
        and bool((event.settlement_cash_account_id or "").strip())
    )


def _resolve_adjustment_amount_and_direction(
    event: TransactionEvent,
) -> tuple[Decimal, str, str]:
    tx_type = normalize_transaction_control_code(event.transaction_type)
    fee = event.trade_fee or Decimal(0)

    resolver = _adjustment_resolvers().get(tx_type)
    if resolver is not None:
        return resolver(event, fee)
    raise AdjustmentCashLegError(
        "transaction_type",
        f"{event.transaction_type} is not eligible for auto-generated cash leg.",
    )


def _adjustment_resolvers() -> dict[str, AdjustmentResolver]:
    return {
        "BUY": _resolve_buy_adjustment,
        "SELL": _resolve_sell_adjustment,
        "DIVIDEND": _resolve_dividend_adjustment,
        "INTEREST": _resolve_interest_adjustment,
    }


def _resolve_buy_adjustment(
    event: TransactionEvent,
    fee: Decimal,
) -> tuple[Decimal, str, str]:
    return event.gross_transaction_amount + fee, "OUTFLOW", "BUY_SETTLEMENT"


def _resolve_sell_adjustment(
    event: TransactionEvent,
    fee: Decimal,
) -> tuple[Decimal, str, str]:
    return event.gross_transaction_amount - fee, "INFLOW", "SELL_SETTLEMENT"


def _resolve_dividend_adjustment(
    event: TransactionEvent,
    fee: Decimal,
) -> tuple[Decimal, str, str]:
    return event.gross_transaction_amount - fee, "INFLOW", "DIVIDEND_SETTLEMENT"


def _resolve_interest_adjustment(
    event: TransactionEvent,
    fee: Decimal,
) -> tuple[Decimal, str, str]:
    net_interest = _resolve_net_interest_amount(event, fee)
    direction = _resolve_interest_movement_direction(event)
    reason = "INTEREST_CHARGE_SETTLEMENT" if direction == "OUTFLOW" else "INTEREST_SETTLEMENT"
    return net_interest, direction, reason


def _resolve_net_interest_amount(event: TransactionEvent, fee: Decimal) -> Decimal:
    if event.net_interest_amount is not None:
        return cast(Decimal, event.net_interest_amount)
    deductions = (event.withholding_tax_amount or Decimal(0)) + (
        event.other_interest_deductions_amount or Decimal(0)
    )
    return cast(Decimal, event.gross_transaction_amount - deductions - fee)


def _resolve_interest_movement_direction(event: TransactionEvent) -> str:
    interest_direction = normalize_transaction_control_code(
        getattr(event, "interest_direction", "INCOME")
    )
    return "OUTFLOW" if interest_direction == "EXPENSE" else "INFLOW"


def build_auto_generated_adjustment_cash_leg(event: TransactionEvent) -> TransactionEvent:
    _require_auto_generate_cash_leg(event)
    _resolve_cash_account_id(event)
    cash_instrument_id = _resolve_cash_instrument_id(event)
    amount, movement_direction, adjustment_reason = _resolve_adjustment_amount_and_direction(event)
    tx_type = normalize_transaction_control_code(event.transaction_type)
    economic_event_id, linked_group_id = _resolve_generated_linkage(event, tx_type)
    return _build_adjustment_cash_leg_event(
        event=event,
        cash_instrument_id=cash_instrument_id,
        amount=abs(amount),
        movement_direction=movement_direction,
        adjustment_reason=adjustment_reason,
        tx_type=tx_type,
        economic_event_id=economic_event_id,
        linked_group_id=linked_group_id,
    )


def _require_auto_generate_cash_leg(event: TransactionEvent) -> None:
    if not should_auto_generate_cash_leg(event):
        raise AdjustmentCashLegError(
            "cash_entry_mode",
            "Event is not configured for AUTO_GENERATE adjustment cash-leg creation.",
        )


def _resolve_cash_account_id(event: TransactionEvent) -> str:
    cash_account_id = (event.settlement_cash_account_id or "").strip()
    if cash_account_id:
        return cash_account_id
    raise AdjustmentCashLegError(
        "settlement_cash_account_id",
        "settlement_cash_account_id is required in AUTO_GENERATE mode.",
    )


def _resolve_cash_instrument_id(event: TransactionEvent) -> str:
    cash_instrument_id = event.settlement_cash_instrument_id or event.settlement_cash_account_id
    if cash_instrument_id:
        return str(cash_instrument_id)
    raise AdjustmentCashLegError(
        "settlement_cash_instrument_id",
        "Unable to resolve settlement cash instrument identifier.",
    )


def _resolve_generated_linkage(event: TransactionEvent, tx_type: str) -> tuple[str, str]:
    economic_event_id = (
        event.economic_event_id or f"EVT-{tx_type}-{event.portfolio_id}-{event.transaction_id}"
    )
    linked_group_id = (
        event.linked_transaction_group_id
        or f"LTG-{tx_type}-{event.portfolio_id}-{event.transaction_id}"
    )
    return economic_event_id, linked_group_id


def _build_adjustment_cash_leg_event(
    *,
    event: TransactionEvent,
    cash_instrument_id: str,
    amount: Decimal,
    movement_direction: str,
    adjustment_reason: str,
    tx_type: str,
    economic_event_id: str,
    linked_group_id: str,
) -> TransactionEvent:
    settlement_dt = event.settlement_date or event.transaction_date

    return TransactionEvent(
        transaction_id=f"{event.transaction_id}-CASHLEG",
        portfolio_id=event.portfolio_id,
        instrument_id=cash_instrument_id,
        security_id=cash_instrument_id,
        transaction_date=settlement_dt,
        settlement_date=settlement_dt,
        transaction_type=ADJUSTMENT_TRANSACTION_TYPE,
        quantity=Decimal(0),
        price=Decimal(0),
        gross_transaction_amount=amount,
        trade_currency=event.trade_currency,
        currency=event.currency,
        trade_fee=Decimal(0),
        economic_event_id=economic_event_id,
        linked_transaction_group_id=linked_group_id,
        calculation_policy_id=event.calculation_policy_id,
        calculation_policy_version=event.calculation_policy_version,
        source_system=event.source_system,
        cash_entry_mode=AUTO_GENERATE_CASH_ENTRY_MODE,
        external_cash_transaction_id=None,
        settlement_cash_account_id=event.settlement_cash_account_id,
        settlement_cash_instrument_id=event.settlement_cash_instrument_id,
        movement_direction=movement_direction,
        originating_transaction_id=event.transaction_id,
        originating_transaction_type=tx_type,
        adjustment_reason=adjustment_reason,
        link_type=f"{tx_type}_TO_CASH",
        reconciliation_key=event.reconciliation_key,
    )
