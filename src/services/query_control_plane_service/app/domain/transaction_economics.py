"""Persistence-independent evidence records for transaction economics products."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class TransactionCashflowEvidence:
    """Latest linked cashflow economics for a booked transaction."""

    amount: Decimal
    currency: str
    classification: str
    timing: str
    is_position_flow: bool
    is_portfolio_flow: bool
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class TransactionCostComponentEvidence:
    """One source-authored fee component attached to a booked transaction."""

    fee_type: str | None
    amount: Decimal
    currency: str | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class BookedTransactionEconomics:
    """Transaction, cost, cashflow, tax, and realized-P&L evidence for read products."""

    transaction_id: str
    portfolio_id: str
    security_id: str
    transaction_type: str
    currency: str
    trade_currency: str | None
    transaction_date: datetime
    gross_transaction_amount: Decimal
    allocated_cost_basis_local: Decimal | None
    allocated_cost_basis_base: Decimal | None
    trade_fee: Decimal | None
    withholding_tax_amount: Decimal | None
    other_interest_deductions_amount: Decimal | None
    net_interest_amount: Decimal | None
    realized_capital_pnl_local: Decimal | None
    realized_fx_pnl_local: Decimal | None
    realized_total_pnl_local: Decimal | None
    realized_capital_pnl_base: Decimal | None
    realized_fx_pnl_base: Decimal | None
    realized_total_pnl_base: Decimal | None
    transaction_fx_rate: Decimal | None
    fx_contract_id: str | None
    cashflow: TransactionCashflowEvidence | None
    costs: tuple[TransactionCostComponentEvidence, ...]
    updated_at: datetime | None
