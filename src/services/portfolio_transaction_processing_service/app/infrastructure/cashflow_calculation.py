"""Map external transaction events and domain cashflows to infrastructure concerns."""

from __future__ import annotations

import logging
from enum import Enum
from typing import Protocol

from portfolio_common.database_models import Cashflow
from portfolio_common.events import TransactionEvent
from portfolio_common.monitoring import CASHFLOWS_CREATED_TOTAL

from ..domain import BookedTransaction
from ..domain.cashflow import (
    TRANSFER_INFLOW_TRANSACTION_TYPES as TRANSFER_INFLOW_TRANSACTION_TYPES,
)
from ..domain.cashflow import (
    TRANSFER_OUTFLOW_TRANSACTION_TYPES as TRANSFER_OUTFLOW_TRANSACTION_TYPES,
)
from ..domain.cashflow import (
    CalculatedCashflow,
    CashflowRule,
    calculate_transaction_cashflow,
)
from .legacy_transaction_event_mapper import to_booked_transaction

logger = logging.getLogger(__name__)


class CashflowRuleView(Protocol):
    """Expose the persisted rule fields needed by domain cashflow policy."""

    classification: str
    timing: str
    is_position_flow: bool
    is_portfolio_flow: bool


class CashflowCalculator:
    """Compatibility adapter for callers that still provide transaction event DTOs."""

    @staticmethod
    def calculate(
        transaction: TransactionEvent,
        rule: CashflowRuleView,
        epoch: int | None = 0,
    ) -> Cashflow:
        """Map an event DTO through the canonical domain policy to a persistence row."""
        return calculate_booked_transaction_cashflow(
            to_booked_transaction(transaction),
            rule,
            epoch=epoch,
        )


def calculate_booked_transaction_cashflow(
    transaction: BookedTransaction,
    rule: CashflowRuleView,
    *,
    epoch: int | None = 0,
) -> Cashflow:
    """Calculate one domain cashflow and adapt it to the existing SQLAlchemy model."""
    return _to_cashflow_row(calculate_observed_transaction_cashflow(transaction, rule, epoch=epoch))


def calculate_observed_transaction_cashflow(
    transaction: BookedTransaction,
    rule: CashflowRuleView,
    *,
    epoch: int | None = 0,
) -> CalculatedCashflow:
    """Calculate a domain cashflow and emit infrastructure observability."""
    calculated = calculate_transaction_cashflow(
        transaction,
        _to_domain_rule(rule),
        epoch=epoch,
    )
    CASHFLOWS_CREATED_TOTAL.labels(
        classification=calculated.classification,
        timing=calculated.timing,
    ).inc()
    logger.info(
        "Calculated cashflow for transaction %s: amount=%s classification=%s",
        calculated.transaction_id,
        calculated.amount,
        calculated.classification,
    )
    return calculated


def _to_domain_rule(rule: CashflowRuleView) -> CashflowRule:
    return CashflowRule(
        classification=_string_value(rule.classification),
        timing=_string_value(rule.timing),
        is_position_flow=rule.is_position_flow,
        is_portfolio_flow=rule.is_portfolio_flow,
    )


def _string_value(value: object) -> str:
    if isinstance(value, Enum):
        value = value.value
    return str(value).strip().upper()


def _to_cashflow_row(cashflow: CalculatedCashflow) -> Cashflow:
    return Cashflow(
        transaction_id=cashflow.transaction_id,
        portfolio_id=cashflow.portfolio_id,
        security_id=cashflow.security_id,
        cashflow_date=cashflow.cashflow_date,
        amount=cashflow.amount,
        currency=cashflow.currency,
        classification=cashflow.classification,
        timing=cashflow.timing,
        calculation_type=cashflow.calculation_type,
        is_position_flow=cashflow.is_position_flow,
        is_portfolio_flow=cashflow.is_portfolio_flow,
        economic_event_id=cashflow.economic_event_id,
        linked_transaction_group_id=cashflow.linked_transaction_group_id,
        epoch=cashflow.epoch,
    )
