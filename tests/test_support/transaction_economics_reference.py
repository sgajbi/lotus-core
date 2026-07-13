"""Independent reference arithmetic for transaction-economics golden vectors."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping


@dataclass(frozen=True, slots=True)
class InterestSettlementReferenceResult:
    """Expected INTEREST amounts calculated without production dependencies."""

    net_interest_amount: Decimal
    settlement_cash_amount: Decimal
    signed_cashflow_amount: Decimal


def evaluate_interest_settlement(
    inputs: Mapping[str, object],
) -> InterestSettlementReferenceResult:
    """Evaluate the reviewed pre-fee-net INTEREST settlement methodology."""
    gross_interest = Decimal(str(inputs["gross_interest_amount"]))
    withholding_tax = Decimal(str(inputs["withholding_tax_amount"]))
    other_deductions = Decimal(str(inputs["other_interest_deductions_amount"]))
    transaction_fee = Decimal(str(inputs["transaction_fee_amount"]))
    expected_net_interest = gross_interest - withholding_tax - other_deductions

    supplied_net_interest = inputs.get("net_interest_amount")
    net_interest = (
        expected_net_interest
        if supplied_net_interest is None
        else Decimal(str(supplied_net_interest))
    )
    if net_interest != expected_net_interest:
        raise ValueError("Explicit net interest does not reconcile to gross less deductions")

    direction = str(inputs["direction"]).strip().upper()
    if direction == "INCOME":
        settlement_cash = net_interest - transaction_fee
        signed_cashflow = settlement_cash
    elif direction == "EXPENSE":
        settlement_cash = net_interest + transaction_fee
        signed_cashflow = -settlement_cash
    else:
        raise ValueError(f"Unsupported interest direction: {direction}")

    return InterestSettlementReferenceResult(
        net_interest_amount=net_interest,
        settlement_cash_amount=settlement_cash,
        signed_cashflow_amount=signed_cashflow,
    )
