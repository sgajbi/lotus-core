from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class BookedTransaction:
    """Framework-neutral booked transaction consumed by calculation policies."""

    transaction_id: str
    portfolio_id: str
    instrument_id: str
    security_id: str
    transaction_date: datetime
    transaction_type: str
    quantity: Decimal
    price: Decimal
    gross_transaction_amount: Decimal
    trade_currency: str
    currency: str
    trade_fee: Decimal | None = Decimal(0)
    brokerage: Decimal | None = None
    stamp_duty: Decimal | None = None
    exchange_fee: Decimal | None = None
    gst: Decimal | None = None
    other_fees: Decimal | None = None
    settlement_date: datetime | None = None
    net_cost: Decimal | None = None
    gross_cost: Decimal | None = None
    realized_gain_loss: Decimal | None = None
    transaction_fx_rate: Decimal | None = None
    net_cost_local: Decimal | None = None
    realized_gain_loss_local: Decimal | None = None
    economic_event_id: str | None = None
    linked_transaction_group_id: str | None = None
    calculation_policy_id: str | None = None
    calculation_policy_version: str | None = None
    source_system: str | None = None
    cash_entry_mode: str | None = None
    external_cash_transaction_id: str | None = None
    settlement_cash_account_id: str | None = None
    settlement_cash_instrument_id: str | None = None
    movement_direction: str | None = None
    originating_transaction_id: str | None = None
    originating_transaction_type: str | None = None
    adjustment_reason: str | None = None
    link_type: str | None = None
    reconciliation_key: str | None = None
    interest_direction: str | None = None
    withholding_tax_amount: Decimal | None = None
    other_interest_deductions_amount: Decimal | None = None
    net_interest_amount: Decimal | None = None
    component_type: str | None = None
    component_id: str | None = None
    linked_component_ids: tuple[str, ...] | None = None
    fx_cash_leg_role: str | None = None
    linked_fx_cash_leg_id: str | None = None
    settlement_status: str | None = None
    pair_base_currency: str | None = None
    pair_quote_currency: str | None = None
    fx_rate_quote_convention: str | None = None
    buy_currency: str | None = None
    sell_currency: str | None = None
    buy_amount: Decimal | None = None
    sell_amount: Decimal | None = None
    contract_rate: Decimal | None = None
    fx_contract_id: str | None = None
    fx_contract_open_transaction_id: str | None = None
    fx_contract_close_transaction_id: str | None = None
    settlement_of_fx_contract_id: str | None = None
    swap_event_id: str | None = None
    near_leg_group_id: str | None = None
    far_leg_group_id: str | None = None
    spot_exposure_model: str | None = None
    fx_realized_pnl_mode: str | None = None
    allocated_cost_basis_local: Decimal | None = None
    allocated_cost_basis_base: Decimal | None = None
    realized_capital_pnl_local: Decimal | None = None
    realized_fx_pnl_local: Decimal | None = None
    realized_total_pnl_local: Decimal | None = None
    realized_capital_pnl_base: Decimal | None = None
    realized_fx_pnl_base: Decimal | None = None
    realized_total_pnl_base: Decimal | None = None
    parent_transaction_reference: str | None = None
    linked_parent_event_id: str | None = None
    parent_event_reference: str | None = None
    child_role: str | None = None
    child_sequence_hint: int | None = None
    dependency_reference_ids: tuple[str, ...] | None = None
    source_instrument_id: str | None = None
    target_instrument_id: str | None = None
    source_transaction_reference: str | None = None
    target_transaction_reference: str | None = None
    linked_cash_transaction_id: str | None = None
    has_synthetic_flow: bool | None = None
    synthetic_flow_effective_date: date | None = None
    synthetic_flow_amount_local: Decimal | None = None
    synthetic_flow_currency: str | None = None
    synthetic_flow_amount_base: Decimal | None = None
    synthetic_flow_fx_rate_to_base: Decimal | None = None
    synthetic_flow_price_used: Decimal | None = None
    synthetic_flow_quantity_used: Decimal | None = None
    synthetic_flow_valuation_method: str | None = None
    synthetic_flow_classification: str | None = None
    synthetic_flow_price_source: str | None = None
    synthetic_flow_fx_source: str | None = None
    synthetic_flow_source: str | None = None
    created_at: datetime | None = None
    epoch: int | None = None
