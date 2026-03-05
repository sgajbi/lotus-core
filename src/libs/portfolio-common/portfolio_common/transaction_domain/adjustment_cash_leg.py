from dataclasses import dataclass
from decimal import Decimal

from portfolio_common.events import TransactionEvent

from .cash_entry_mode import AUTO_GENERATE_CASH_ENTRY_MODE, normalize_cash_entry_mode

ADJUSTMENT_TRANSACTION_TYPE = "ADJUSTMENT"

AUTO_GENERATE_ELIGIBLE_TRANSACTION_TYPES = {
    "BUY",
    "SELL",
    "DIVIDEND",
    "INTEREST",
}


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
    return (
        mode == AUTO_GENERATE_CASH_ENTRY_MODE
        and event.transaction_type.upper() in AUTO_GENERATE_ELIGIBLE_TRANSACTION_TYPES
        and bool((event.settlement_cash_account_id or "").strip())
    )


def _resolve_adjustment_amount_and_direction(
    event: TransactionEvent,
) -> tuple[Decimal, str, str]:
    tx_type = event.transaction_type.upper()
    fee = event.trade_fee or Decimal(0)

    if tx_type == "BUY":
        return event.gross_transaction_amount + fee, "OUTFLOW", "BUY_SETTLEMENT"
    if tx_type == "SELL":
        return event.gross_transaction_amount - fee, "INFLOW", "SELL_SETTLEMENT"
    if tx_type == "DIVIDEND":
        return event.gross_transaction_amount - fee, "INFLOW", "DIVIDEND_SETTLEMENT"
    if tx_type == "INTEREST":
        deductions = (event.withholding_tax_amount or Decimal(0)) + (
            event.other_interest_deductions_amount or Decimal(0)
        )
        net_interest = event.net_interest_amount
        if net_interest is None:
            net_interest = event.gross_transaction_amount - deductions - fee
        direction = (
            "OUTFLOW"
            if str(getattr(event, "interest_direction", "INCOME")).upper() == "EXPENSE"
            else "INFLOW"
        )
        reason = "INTEREST_CHARGE_SETTLEMENT" if direction == "OUTFLOW" else "INTEREST_SETTLEMENT"
        return net_interest, direction, reason
    raise AdjustmentCashLegError(
        "transaction_type",
        f"{event.transaction_type} is not eligible for auto-generated cash leg.",
    )


def build_auto_generated_adjustment_cash_leg(event: TransactionEvent) -> TransactionEvent:
    if not should_auto_generate_cash_leg(event):
        raise AdjustmentCashLegError(
            "cash_entry_mode",
            "Event is not configured for AUTO_GENERATE adjustment cash-leg creation.",
        )

    cash_account_id = (event.settlement_cash_account_id or "").strip()
    if not cash_account_id:
        raise AdjustmentCashLegError(
            "settlement_cash_account_id",
            "settlement_cash_account_id is required in AUTO_GENERATE mode.",
        )

    cash_instrument_id = event.settlement_cash_instrument_id or event.settlement_cash_account_id
    if not cash_instrument_id:
        raise AdjustmentCashLegError(
            "settlement_cash_instrument_id",
            "Unable to resolve settlement cash instrument identifier.",
        )

    amount, movement_direction, adjustment_reason = _resolve_adjustment_amount_and_direction(event)
    amount = abs(amount)

    tx_type = event.transaction_type.upper()
    economic_event_id = (
        event.economic_event_id or f"EVT-{tx_type}-{event.portfolio_id}-{event.transaction_id}"
    )
    linked_group_id = (
        event.linked_transaction_group_id
        or f"LTG-{tx_type}-{event.portfolio_id}-{event.transaction_id}"
    )
    settlement_dt = event.settlement_date or event.transaction_date

    return TransactionEvent(
        transaction_id=f"{event.transaction_id}-CASHLEG",
        portfolio_id=event.portfolio_id,
        instrument_id=str(cash_instrument_id),
        security_id=str(cash_instrument_id),
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
