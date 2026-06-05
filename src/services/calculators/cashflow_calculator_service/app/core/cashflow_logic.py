import logging
from decimal import Decimal
from typing import Optional, Protocol

from portfolio_common.database_models import Cashflow
from portfolio_common.events import TransactionEvent
from portfolio_common.monitoring import CASHFLOWS_CREATED_TOTAL
from portfolio_common.transaction_fee_components import (
    TRANSACTION_FEE_COMPONENT_FIELDS,
    resolve_transaction_trade_fee,
)

from .enums import CashflowClassification

logger = logging.getLogger(__name__)

TRANSFER_INFLOW_TRANSACTION_TYPES = {
    "TRANSFER_IN",
    "MERGER_IN",
    "EXCHANGE_IN",
    "REPLACEMENT_IN",
    "SPIN_IN",
    "DEMERGER_IN",
    "SPLIT",
    "BONUS_ISSUE",
    "STOCK_DIVIDEND",
    "RIGHTS_ALLOCATE",
    "RIGHTS_SHARE_DELIVERY",
    "RIGHTS_REFUND",
}
TRANSFER_OUTFLOW_TRANSACTION_TYPES = {
    "TRANSFER_OUT",
    "MERGER_OUT",
    "EXCHANGE_OUT",
    "REPLACEMENT_OUT",
    "SPIN_OFF",
    "DEMERGER_OUT",
    "REVERSE_SPLIT",
    "CONSOLIDATION",
    "RIGHTS_SUBSCRIBE",
    "RIGHTS_OVERSUBSCRIBE",
    "RIGHTS_SELL",
    "RIGHTS_EXPIRE",
}
CLASSIFICATION_SIGN_FACTORS = {
    CashflowClassification.FX_BUY: 1,
    CashflowClassification.FX_SELL: -1,
    CashflowClassification.INVESTMENT_INFLOW: 1,
    CashflowClassification.INCOME: 1,
    CashflowClassification.CASHFLOW_IN: 1,
}


def _normalize_code(value: object, default: str = "") -> str:
    return str(value or default).strip().upper()


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
        return transaction.gross_transaction_amount + trade_fee
    return transaction.gross_transaction_amount - trade_fee


def _interest_cashflow_amount(transaction: TransactionEvent, trade_fee: Decimal) -> Decimal:
    deductions = (transaction.withholding_tax_amount or Decimal(0)) + (
        transaction.other_interest_deductions_amount or Decimal(0)
    )
    if transaction.net_interest_amount is not None:
        return transaction.net_interest_amount
    return transaction.gross_transaction_amount - deductions - trade_fee


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


def _signed_by_classification(classification: str, amount: Decimal) -> Decimal:
    sign_factor = CLASSIFICATION_SIGN_FACTORS.get(classification, -1)
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


class CashflowLogic:
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
        amount = _signed_cashflow_amount(
            transaction,
            rule,
            transaction_type,
            _base_cashflow_amount(transaction, transaction_type),
        )

        # Create the Cashflow database object
        cashflow = Cashflow(
            transaction_id=transaction.transaction_id,
            portfolio_id=transaction.portfolio_id,
            security_id=transaction.security_id,
            cashflow_date=transaction.transaction_date.date(),
            amount=amount,
            currency=transaction.currency,
            classification=rule.classification,
            timing=rule.timing,
            calculation_type="NET",  # Currently all are NET
            is_position_flow=rule.is_position_flow,
            is_portfolio_flow=rule.is_portfolio_flow,
            economic_event_id=transaction.economic_event_id,
            linked_transaction_group_id=transaction.linked_transaction_group_id,
            epoch=epoch or 0,
        )

        # Increment the Prometheus counter
        CASHFLOWS_CREATED_TOTAL.labels(classification=rule.classification, timing=rule.timing).inc()

        logger.info(
            "Calculated cashflow for txn "
            f"{transaction.transaction_id}: Amount={amount}, "
            f"Class='{rule.classification}'"
        )
        return cashflow


class CashflowRuleView(Protocol):
    classification: str
    timing: str
    is_position_flow: bool
    is_portfolio_flow: bool
