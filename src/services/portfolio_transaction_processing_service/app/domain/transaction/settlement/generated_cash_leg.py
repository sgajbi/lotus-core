"""Calculate the settlement cash leg generated for a booked product transaction."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

from portfolio_common.domain.transaction_control_codes import (
    normalize_transaction_control_code,
)
from portfolio_common.transaction_type_registry import TRANSACTION_TYPE_REGISTRY

from ..booked import BookedTransaction
from .cash_entry import CashEntryMode, resolve_cash_entry_mode

ADJUSTMENT_TRANSACTION_TYPE = "ADJUSTMENT"

AUTO_GENERATE_ELIGIBLE_TRANSACTION_TYPES = frozenset(
    code
    for code, definition in TRANSACTION_TYPE_REGISTRY.items()
    if definition.production_booking_allowed
    and definition.lifecycle_family in {"trade", "income"}
    and definition.cash_effect in {"inflow", "outflow"}
    and definition.settlement_behavior == "requires_cash_leg"
)

CashLegEconomicsResolver = Callable[
    [BookedTransaction, Decimal],
    tuple[Decimal, str, str],
]


@dataclass(frozen=True, slots=True)
class GeneratedCashLegError(ValueError):
    """Describe why a product transaction cannot produce a settlement cash leg."""

    field: str
    message: str

    def __str__(self) -> str:
        return f"{self.field}: {self.message}"


def should_generate_settlement_cash_leg(transaction: BookedTransaction) -> bool:
    """Return whether Core must generate a settlement cash leg for the transaction."""

    if transaction.cash_entry_mode is None:
        return False
    mode = resolve_cash_entry_mode(transaction.cash_entry_mode)
    transaction_type = normalize_transaction_control_code(transaction.transaction_type)
    return (
        mode is CashEntryMode.AUTO_GENERATE
        and transaction_type in AUTO_GENERATE_ELIGIBLE_TRANSACTION_TYPES
        and bool((transaction.settlement_cash_account_id or "").strip())
    )


def build_generated_settlement_cash_leg(
    transaction: BookedTransaction,
) -> BookedTransaction:
    """Build the equal-and-linked cash movement for a supported product transaction."""

    _require_generated_cash_leg(transaction)
    cash_instrument_id = _resolve_cash_instrument_id(transaction)
    amount, movement_direction, adjustment_reason = _resolve_cash_leg_economics(transaction)
    transaction_type = normalize_transaction_control_code(transaction.transaction_type)
    economic_event_id, linked_group_id = _resolve_generated_linkage(
        transaction,
        transaction_type,
    )
    settlement_at = transaction.settlement_date or transaction.transaction_date
    return BookedTransaction(
        transaction_id=f"{transaction.transaction_id}-CASHLEG",
        portfolio_id=transaction.portfolio_id,
        instrument_id=cash_instrument_id,
        security_id=cash_instrument_id,
        transaction_date=settlement_at,
        settlement_date=settlement_at,
        transaction_type=ADJUSTMENT_TRANSACTION_TYPE,
        quantity=Decimal(0),
        price=Decimal(0),
        gross_transaction_amount=abs(amount),
        trade_currency=transaction.trade_currency,
        currency=transaction.currency,
        trade_fee=Decimal(0),
        economic_event_id=economic_event_id,
        linked_transaction_group_id=linked_group_id,
        calculation_policy_id=transaction.calculation_policy_id,
        calculation_policy_version=transaction.calculation_policy_version,
        source_system=transaction.source_system,
        cash_entry_mode=CashEntryMode.AUTO_GENERATE.value,
        settlement_cash_account_id=transaction.settlement_cash_account_id,
        settlement_cash_instrument_id=transaction.settlement_cash_instrument_id,
        movement_direction=movement_direction,
        originating_transaction_id=transaction.transaction_id,
        originating_transaction_type=transaction_type,
        adjustment_reason=adjustment_reason,
        link_type=f"{transaction_type}_TO_CASH",
        reconciliation_key=transaction.reconciliation_key,
    )


def _require_generated_cash_leg(transaction: BookedTransaction) -> None:
    if should_generate_settlement_cash_leg(transaction):
        return
    raise GeneratedCashLegError(
        "cash_entry_mode",
        "Event is not configured for AUTO_GENERATE adjustment cash-leg creation.",
    )


def _resolve_cash_instrument_id(transaction: BookedTransaction) -> str:
    cash_instrument_id = (
        transaction.settlement_cash_instrument_id or transaction.settlement_cash_account_id
    )
    if cash_instrument_id:
        return str(cash_instrument_id)
    raise GeneratedCashLegError(
        "settlement_cash_instrument_id",
        "Unable to resolve settlement cash instrument identifier.",
    )


def _resolve_cash_leg_economics(
    transaction: BookedTransaction,
) -> tuple[Decimal, str, str]:
    transaction_type = normalize_transaction_control_code(transaction.transaction_type)
    fee = transaction.trade_fee or Decimal(0)
    resolver = _cash_leg_economics_resolvers().get(transaction_type)
    if resolver is None:
        raise GeneratedCashLegError(
            "transaction_type",
            f"{transaction.transaction_type} is not eligible for auto-generated cash leg.",
        )
    return resolver(transaction, fee)


def _cash_leg_economics_resolvers() -> dict[str, CashLegEconomicsResolver]:
    return {
        "BUY": _resolve_buy_cash_leg,
        "SELL": _resolve_sell_cash_leg,
        "DIVIDEND": _resolve_dividend_cash_leg,
        "INTEREST": _resolve_interest_cash_leg,
    }


def _resolve_buy_cash_leg(
    transaction: BookedTransaction,
    fee: Decimal,
) -> tuple[Decimal, str, str]:
    return transaction.gross_transaction_amount + fee, "OUTFLOW", "BUY_SETTLEMENT"


def _resolve_sell_cash_leg(
    transaction: BookedTransaction,
    fee: Decimal,
) -> tuple[Decimal, str, str]:
    return transaction.gross_transaction_amount - fee, "INFLOW", "SELL_SETTLEMENT"


def _resolve_dividend_cash_leg(
    transaction: BookedTransaction,
    fee: Decimal,
) -> tuple[Decimal, str, str]:
    return transaction.gross_transaction_amount - fee, "INFLOW", "DIVIDEND_SETTLEMENT"


def _resolve_interest_cash_leg(
    transaction: BookedTransaction,
    fee: Decimal,
) -> tuple[Decimal, str, str]:
    amount = _resolve_net_interest_amount(transaction, fee)
    direction = _resolve_interest_movement_direction(transaction)
    reason = "INTEREST_CHARGE_SETTLEMENT" if direction == "OUTFLOW" else "INTEREST_SETTLEMENT"
    return amount, direction, reason


def _resolve_net_interest_amount(
    transaction: BookedTransaction,
    fee: Decimal,
) -> Decimal:
    if transaction.net_interest_amount is not None:
        return transaction.net_interest_amount
    deductions = (transaction.withholding_tax_amount or Decimal(0)) + (
        transaction.other_interest_deductions_amount or Decimal(0)
    )
    return transaction.gross_transaction_amount - deductions - fee


def _resolve_interest_movement_direction(transaction: BookedTransaction) -> str:
    interest_direction = normalize_transaction_control_code(
        transaction.interest_direction or "INCOME"
    )
    return "OUTFLOW" if interest_direction == "EXPENSE" else "INFLOW"


def _resolve_generated_linkage(
    transaction: BookedTransaction,
    transaction_type: str,
) -> tuple[str, str]:
    economic_event_id = transaction.economic_event_id or (
        f"EVT-{transaction_type}-{transaction.portfolio_id}-{transaction.transaction_id}"
    )
    linked_group_id = transaction.linked_transaction_group_id or (
        f"LTG-{transaction_type}-{transaction.portfolio_id}-{transaction.transaction_id}"
    )
    return economic_event_id, linked_group_id
