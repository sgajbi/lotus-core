"""Resolve canonical INTEREST net amounts and settlement cash economics."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from portfolio_common.domain.transaction.fee_components import (
    TRANSACTION_FEE_COMPONENT_FIELDS,
    resolve_transaction_trade_fee,
)
from portfolio_common.domain.transaction.interest_economics import (
    calculate_interest_pre_fee_net,
)
from portfolio_common.domain.transaction_control_codes import (
    normalize_transaction_control_code,
)

from ..booked import BookedTransaction


@dataclass(frozen=True, slots=True)
class InterestSettlementEconomics:
    """Carry reconciled interest amounts and the direction-neutral cash magnitude."""

    expected_net_interest_amount: Decimal
    net_interest_amount: Decimal
    transaction_fee_amount: Decimal
    settlement_cash_amount: Decimal


def calculate_interest_settlement_economics(
    transaction: BookedTransaction,
) -> InterestSettlementEconomics:
    """Calculate INTEREST net amount and fee-adjusted settlement cash magnitude.

    ``net_interest_amount`` is the amount after withholding tax and other interest
    deductions but before transaction fees. Fees reduce an income receipt and
    increase an expense payment.
    """

    expected_net_interest = calculate_interest_pre_fee_net(
        gross_transaction_amount=transaction.gross_transaction_amount,
        withholding_tax_amount=transaction.withholding_tax_amount,
        other_interest_deductions_amount=transaction.other_interest_deductions_amount,
    )
    net_interest = (
        transaction.net_interest_amount
        if transaction.net_interest_amount is not None
        else expected_net_interest
    )
    transaction_fee = resolve_transaction_trade_fee(
        transaction.trade_fee,
        {field: getattr(transaction, field) for field in TRANSACTION_FEE_COMPONENT_FIELDS},
    ) or Decimal(0)
    interest_direction = normalize_transaction_control_code(
        transaction.interest_direction or "INCOME"
    )
    settlement_cash = (
        net_interest + transaction_fee
        if interest_direction == "EXPENSE"
        else net_interest - transaction_fee
    )
    return InterestSettlementEconomics(
        expected_net_interest_amount=expected_net_interest,
        net_interest_amount=net_interest,
        transaction_fee_amount=transaction_fee,
        settlement_cash_amount=settlement_cash,
    )
