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


@dataclass(frozen=True, slots=True)
class OrdinarySettlementCashReferenceResult:
    """Expected ordinary settlement outcome calculated without production dependencies."""

    available_proceeds_amount: Decimal
    fee_amount: Decimal
    signed_cash_amount: Decimal | None
    rejection_reason_code: str | None

    @property
    def accepted(self) -> bool:
        """Return whether the reference policy produced a ledger movement."""

        return self.rejection_reason_code is None


@dataclass(frozen=True, slots=True)
class DividendSettlementReferenceResult:
    """Expected DIVIDEND settlement and unchanged-position economics."""

    settlement_cash_amount: Decimal
    signed_cashflow_amount: Decimal
    quantity_delta: Decimal
    cost_basis_delta: Decimal
    cost_basis_local_delta: Decimal
    net_cost_amount: Decimal
    net_cost_local_amount: Decimal
    realized_total_pnl: Decimal
    realized_total_pnl_local: Decimal


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


def evaluate_ordinary_settlement_cash(
    inputs: Mapping[str, object],
) -> OrdinarySettlementCashReferenceResult:
    """Evaluate reviewed SELL, DIVIDEND, and INTEREST settlement boundaries."""

    transaction_type = str(inputs["transaction_type"]).strip().upper()
    fee = Decimal(str(inputs["transaction_fee_amount"]))
    if transaction_type in {"SELL", "DIVIDEND"}:
        available_proceeds = Decimal(str(inputs["gross_transaction_amount"]))
        settlement_amount = available_proceeds - fee
        signed_cash = settlement_amount
        reason_code = {
            "SELL": "SELL_010_NON_POSITIVE_NET_SETTLEMENT",
            "DIVIDEND": "DIVIDEND_013_NON_POSITIVE_NET_SETTLEMENT",
        }[transaction_type]
    elif transaction_type == "INTEREST":
        interest = evaluate_interest_settlement(inputs)
        available_proceeds = interest.net_interest_amount
        settlement_amount = interest.settlement_cash_amount
        signed_cash = interest.signed_cashflow_amount
        reason_code = "INTEREST_017_NON_POSITIVE_NET_SETTLEMENT"
    else:
        raise ValueError(f"Unsupported ordinary settlement type: {transaction_type}")

    if settlement_amount <= 0:
        return OrdinarySettlementCashReferenceResult(
            available_proceeds_amount=available_proceeds,
            fee_amount=fee,
            signed_cash_amount=None,
            rejection_reason_code=reason_code,
        )
    return OrdinarySettlementCashReferenceResult(
        available_proceeds_amount=available_proceeds,
        fee_amount=fee,
        signed_cash_amount=signed_cash,
        rejection_reason_code=None,
    )


def evaluate_dividend_settlement(
    inputs: Mapping[str, object],
) -> DividendSettlementReferenceResult:
    """Evaluate supported DIVIDEND cash and zero-position-impact economics."""
    gross_dividend = Decimal(str(inputs["gross_dividend_amount"]))
    transaction_fee = Decimal(str(inputs["transaction_fee_amount"]))
    settlement_cash = gross_dividend - transaction_fee
    if gross_dividend <= Decimal(0):
        raise ValueError("DIVIDEND gross amount must be greater than zero")
    if settlement_cash <= Decimal(0):
        raise ValueError("DIVIDEND settlement cash must remain greater than zero")
    return DividendSettlementReferenceResult(
        settlement_cash_amount=settlement_cash,
        signed_cashflow_amount=settlement_cash,
        quantity_delta=Decimal(0),
        cost_basis_delta=Decimal(0),
        cost_basis_local_delta=Decimal(0),
        net_cost_amount=Decimal(0),
        net_cost_local_amount=Decimal(0),
        realized_total_pnl=Decimal(0),
        realized_total_pnl_local=Decimal(0),
    )
