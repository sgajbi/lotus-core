from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True)
class PortfolioTaxLotReadRecord:
    portfolio_id: str
    security_id: str
    instrument_id: str
    lot_id: str
    open_quantity: Decimal
    original_quantity: Decimal
    acquisition_date: date
    lot_cost_base: Decimal
    lot_cost_local: Decimal
    source_transaction_id: str
    source_system: str | None
    calculation_policy_id: str | None
    calculation_policy_version: str | None
    local_currency: str | None
    updated_at: datetime | None


@dataclass(frozen=True)
class PerformanceEconomicsCashflowReadRecord:
    amount: Decimal
    currency: str
    classification: str
    timing: str
    is_position_flow: bool
    is_portfolio_flow: bool
    updated_at: datetime | None


@dataclass(frozen=True)
class PerformanceEconomicsCostReadRecord:
    fee_type: str | None
    amount: Decimal
    currency: str | None
    updated_at: datetime | None


@dataclass(frozen=True)
class PerformanceEconomicsTransactionReadRecord:
    transaction_id: str
    portfolio_id: str
    security_id: str
    transaction_type: str
    currency: str
    trade_currency: str | None
    transaction_date: datetime
    gross_transaction_amount: Decimal
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
    cashflow: PerformanceEconomicsCashflowReadRecord | None
    costs: tuple[PerformanceEconomicsCostReadRecord, ...]
    updated_at: datetime | None
