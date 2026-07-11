"""Calculate persisted cashflow records from governed transaction rules."""

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional, Protocol, cast

from portfolio_common.database_models import Cashflow
from portfolio_common.events import TransactionEvent
from portfolio_common.monitoring import CASHFLOWS_CREATED_TOTAL
from portfolio_common.transaction_fee_components import (
    TRANSACTION_FEE_COMPONENT_FIELDS,
    resolve_transaction_trade_fee,
)
from portfolio_common.transaction_type_registry import TRANSACTION_TYPE_REGISTRY

from ..domain.cashflow import CashflowCalculationType, CashflowClassification

logger = logging.getLogger(__name__)

_TRANSFER_SIGNING_LIFECYCLE_FAMILIES = {"transfer", "corporate_action", "rights"}
_TRANSFER_SIGNING_INFLOW_CASH_EFFECT_TYPES = {"RIGHTS_REFUND"}
_TRANSFER_SIGNING_FALLBACK_TYPES = {"CASH_IN_LIEU"}
_SETTLEMENT_DATED_CASHFLOW_TYPES = frozenset(
    {
        "BUY",
        "SELL",
        "DEPOSIT",
        "WITHDRAWAL",
        "FX_CASH_SETTLEMENT_BUY",
        "FX_CASH_SETTLEMENT_SELL",
    }
)
_PAYMENT_DATED_CASHFLOW_TYPES = frozenset({"DIVIDEND", "INTEREST"})


def _transfer_signing_types_for_position_effect(position_effect: str) -> frozenset[str]:
    return frozenset(
        code
        for code, definition in TRANSACTION_TYPE_REGISTRY.items()
        if definition.production_booking_allowed
        and definition.lifecycle_family in _TRANSFER_SIGNING_LIFECYCLE_FAMILIES
        and definition.position_effect == position_effect
        and code not in _TRANSFER_SIGNING_FALLBACK_TYPES
    )


TRANSFER_INFLOW_TRANSACTION_TYPES = (
    _transfer_signing_types_for_position_effect("increase")
    | _TRANSFER_SIGNING_INFLOW_CASH_EFFECT_TYPES
)
TRANSFER_OUTFLOW_TRANSACTION_TYPES = _transfer_signing_types_for_position_effect("decrease")
CLASSIFICATION_SIGN_FACTORS: dict[str, int] = {
    CashflowClassification.FX_BUY.value: 1,
    CashflowClassification.FX_SELL.value: -1,
    CashflowClassification.INVESTMENT_INFLOW.value: 1,
    CashflowClassification.CORPORATE_ACTION_PROCEEDS.value: 1,
    CashflowClassification.INCOME.value: 1,
    CashflowClassification.CASHFLOW_IN.value: 1,
}
_SYNTHETIC_TRANSFER_CLASSIFICATION_SIGN = {
    "POSITION_TRANSFER_IN": 1,
    "POSITION_TRANSFER_OUT": -1,
    "POSITION_CASH_IN_LIEU_OUT": -1,
}


@dataclass(frozen=True, slots=True)
class CashflowEconomics:
    amount: Decimal
    currency: str
    calculation_type: str


@dataclass(frozen=True, slots=True)
class CashflowLevel:
    is_position_flow: bool
    is_portfolio_flow: bool


def _normalize_code(value: object, default: str = "") -> str:
    return str(value or default).strip().upper()


def _normalize_classification(value: object) -> str:
    if isinstance(value, CashflowClassification):
        return cast(str, value.value)
    return _normalize_code(value)


def _transaction_date(transaction: TransactionEvent) -> date:
    return cast(date, transaction.transaction_date.date())


def _settlement_date_or_transaction_date(transaction: TransactionEvent) -> date:
    if transaction.settlement_date is not None:
        return cast(date, transaction.settlement_date.date())
    return _transaction_date(transaction)


def _resolve_cashflow_date(
    transaction: TransactionEvent,
    rule: "CashflowRuleView",
    transaction_type: str,
) -> date:
    if transaction.synthetic_flow_effective_date is not None:
        return cast(date, transaction.synthetic_flow_effective_date)
    if transaction_type in _SETTLEMENT_DATED_CASHFLOW_TYPES:
        return _settlement_date_or_transaction_date(transaction)
    if transaction_type in _PAYMENT_DATED_CASHFLOW_TYPES:
        return _settlement_date_or_transaction_date(transaction)
    if _normalize_classification(rule.classification) in {"FX_BUY", "FX_SELL"}:
        return _settlement_date_or_transaction_date(transaction)
    return _transaction_date(transaction)


def _resolve_cashflow_trade_fee(transaction: TransactionEvent) -> Decimal:
    trade_fee = resolve_transaction_trade_fee(
        transaction.trade_fee,
        {field: getattr(transaction, field) for field in TRANSACTION_FEE_COMPONENT_FIELDS},
    )
    return trade_fee or Decimal(0)


def _base_cashflow_amount(transaction: TransactionEvent, transaction_type: str) -> Decimal:
    trade_fee = _resolve_cashflow_trade_fee(transaction)
    if transaction_type == "INTEREST":
        return _interest_cashflow_amount(transaction, trade_fee)
    if transaction_type in {"BUY", "FEE"}:
        return cast(Decimal, transaction.gross_transaction_amount + trade_fee)
    return cast(Decimal, transaction.gross_transaction_amount - trade_fee)


def _interest_cashflow_amount(transaction: TransactionEvent, trade_fee: Decimal) -> Decimal:
    deductions = (transaction.withholding_tax_amount or Decimal(0)) + (
        transaction.other_interest_deductions_amount or Decimal(0)
    )
    if transaction.net_interest_amount is not None:
        return cast(Decimal, transaction.net_interest_amount)
    return cast(Decimal, transaction.gross_transaction_amount - deductions - trade_fee)


def _signed_cashflow_amount(
    transaction: TransactionEvent,
    rule: "CashflowRuleView",
    transaction_type: str,
    amount: Decimal,
) -> Decimal:
    if transaction_type == "INTEREST":
        return _signed_interest_amount(transaction, amount)
    if transaction_type == "ADJUSTMENT":
        return _signed_adjustment_amount(transaction, amount)
    if rule.classification == CashflowClassification.TRANSFER:
        return _signed_transfer_amount(transaction, transaction_type, amount)
    return _signed_by_classification(rule.classification, amount)


def _resolve_cashflow_economics(
    transaction: TransactionEvent,
    rule: "CashflowRuleView",
    transaction_type: str,
) -> CashflowEconomics:
    if transaction.has_synthetic_flow:
        return _synthetic_transfer_economics(transaction, rule)
    amount = _signed_cashflow_amount(
        transaction,
        rule,
        transaction_type,
        _base_cashflow_amount(transaction, transaction_type),
    )
    return CashflowEconomics(
        amount=amount,
        currency=transaction.currency,
        calculation_type=CashflowCalculationType.NET.value,
    )


def _synthetic_transfer_economics(
    transaction: TransactionEvent,
    rule: "CashflowRuleView",
) -> CashflowEconomics:
    classification = _normalize_code(transaction.synthetic_flow_classification)
    sign = _SYNTHETIC_TRANSFER_CLASSIFICATION_SIGN.get(classification)
    if _normalize_classification(rule.classification) != CashflowClassification.TRANSFER.value:
        raise ValueError("Synthetic position flow requires TRANSFER cashflow classification")
    if not rule.is_position_flow or rule.is_portfolio_flow:
        raise ValueError("Synthetic position flow must be position-level and non-portfolio")
    if sign is None:
        raise ValueError("Synthetic position flow classification is missing or unsupported")
    if transaction.synthetic_flow_amount_local is None:
        raise ValueError("Synthetic position flow amount is required")
    if not transaction.synthetic_flow_currency:
        raise ValueError("Synthetic position flow currency is required")

    amount = transaction.synthetic_flow_amount_local
    if amount.is_zero() or (amount > 0) != (sign > 0):
        raise ValueError("Synthetic position flow amount sign does not match its classification")
    return CashflowEconomics(
        amount=amount,
        currency=transaction.synthetic_flow_currency,
        calculation_type=CashflowCalculationType.MVT.value,
    )


def _resolve_cashflow_level(
    transaction: TransactionEvent,
    rule: "CashflowRuleView",
) -> CashflowLevel:
    if _is_duplicate_corporate_action_cash_settlement(transaction):
        return CashflowLevel(is_position_flow=False, is_portfolio_flow=False)
    return CashflowLevel(
        is_position_flow=rule.is_position_flow,
        is_portfolio_flow=rule.is_portfolio_flow,
    )


def _is_duplicate_corporate_action_cash_settlement(transaction: TransactionEvent) -> bool:
    return (
        _normalize_code(transaction.transaction_type) == "ADJUSTMENT"
        and bool((transaction.originating_transaction_id or "").strip())
        and _normalize_code(transaction.originating_transaction_type)
        in {"CASH_CONSIDERATION", "CASH_IN_LIEU"}
    )


def _signed_by_classification(classification: str, amount: Decimal) -> Decimal:
    sign_factor = CLASSIFICATION_SIGN_FACTORS.get(_normalize_classification(classification), -1)
    return abs(amount) if sign_factor > 0 else -abs(amount)


def _signed_interest_amount(transaction: TransactionEvent, amount: Decimal) -> Decimal:
    interest_direction = _normalize_code(
        getattr(transaction, "interest_direction", None),
        default="INCOME",
    )
    return -abs(amount) if interest_direction == "EXPENSE" else abs(amount)


def _signed_adjustment_amount(transaction: TransactionEvent, amount: Decimal) -> Decimal:
    movement_direction = _normalize_code(
        getattr(transaction, "movement_direction", None),
        default="INFLOW",
    )
    return abs(amount) if movement_direction == "INFLOW" else -abs(amount)


def _signed_transfer_amount(
    transaction: TransactionEvent,
    transaction_type: str,
    amount: Decimal,
) -> Decimal:
    if transaction_type in TRANSFER_INFLOW_TRANSACTION_TYPES:
        return abs(amount)
    if transaction_type in TRANSFER_OUTFLOW_TRANSACTION_TYPES:
        return -abs(amount)
    return abs(amount) if transaction.quantity > 0 else -abs(amount)


class CashflowCalculator:
    """
    A stateless calculator that generates a Cashflow object from a transaction
    based on a given business rule from the database.
    """

    @staticmethod
    def calculate(
        transaction: TransactionEvent, rule: "CashflowRuleView", epoch: Optional[int] = 0
    ) -> Cashflow:
        """
        Applies the calculation rule to a transaction to generate a cashflow.
        """
        transaction_type = _normalize_code(transaction.transaction_type)
        economics = _resolve_cashflow_economics(transaction, rule, transaction_type)
        level = _resolve_cashflow_level(transaction, rule)

        # Create the Cashflow database object
        cashflow = Cashflow(
            transaction_id=transaction.transaction_id,
            portfolio_id=transaction.portfolio_id,
            security_id=transaction.security_id,
            cashflow_date=_resolve_cashflow_date(transaction, rule, transaction_type),
            amount=economics.amount,
            currency=economics.currency,
            classification=rule.classification,
            timing=rule.timing,
            calculation_type=economics.calculation_type,
            is_position_flow=level.is_position_flow,
            is_portfolio_flow=level.is_portfolio_flow,
            economic_event_id=transaction.economic_event_id,
            linked_transaction_group_id=transaction.linked_transaction_group_id,
            epoch=epoch or 0,
        )

        # Increment the Prometheus counter
        CASHFLOWS_CREATED_TOTAL.labels(classification=rule.classification, timing=rule.timing).inc()

        logger.info(
            "Calculated cashflow for txn "
            f"{transaction.transaction_id}: Amount={economics.amount}, "
            f"Class='{rule.classification}'"
        )
        return cashflow


# Temporary source-compatible name while transaction RFC tests migrate terminology.
class CashflowRuleView(Protocol):
    classification: str
    timing: str
    is_position_flow: bool
    is_portfolio_flow: bool
