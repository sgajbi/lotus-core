# libs/portfolio-common/portfolio_common/events.py
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .ca_bundle_a_ordering import (
    ca_bundle_a_dependency_rank,
    ca_bundle_a_target_order_key,
)


class BusinessDateEvent(BaseModel):
    """Event model for a raw business date."""

    model_config = ConfigDict(from_attributes=True)
    business_date: date = Field(...)
    calendar_code: str = Field("GLOBAL")
    market_code: Optional[str] = Field(None)
    source_system: Optional[str] = Field(None)
    source_batch_id: Optional[str] = Field(None)


class PortfolioEvent(BaseModel):
    """
    Event model for raw portfolio data.
    """

    model_config = ConfigDict(from_attributes=True)

    portfolio_id: str = Field(...)
    base_currency: str = Field(...)
    open_date: date = Field(...)
    close_date: Optional[date] = Field(None)
    risk_exposure: str = Field(...)
    investment_time_horizon: str = Field(...)
    portfolio_type: str = Field(...)
    objective: Optional[str] = None
    booking_center_code: str = Field(...)
    client_id: str = Field(...)
    is_leverage_allowed: bool = Field(False)
    advisor_id: Optional[str] = Field(None)
    status: str
    cost_basis_method: Optional[str] = Field("FIFO")


class FxRateEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_currency: str = Field(...)
    to_currency: str = Field(...)
    rate_date: date = Field(...)
    rate: Decimal


class MarketPriceEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    security_id: str = Field(...)
    price_date: date = Field(...)
    price: Decimal
    currency: str


class MarketPricePersistedEvent(BaseModel):
    """
    Event published after a market price has been successfully persisted.
    """

    model_config = ConfigDict(from_attributes=True)

    security_id: str
    price_date: date
    price: Decimal
    currency: str


class InstrumentEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    security_id: str = Field(...)
    name: str
    isin: str
    currency: str = Field(...)
    product_type: str = Field(...)
    asset_class: Optional[str] = Field(None)
    sector: Optional[str] = None
    country_of_risk: Optional[str] = Field(None)
    rating: Optional[str] = None
    maturity_date: Optional[date] = Field(None)
    issuer_id: Optional[str] = Field(None)
    issuer_name: Optional[str] = Field(None)
    ultimate_parent_issuer_id: Optional[str] = Field(None)
    ultimate_parent_issuer_name: Optional[str] = Field(None)


class TransactionEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    trade_fee: Optional[Decimal] = Field(default=Decimal(0))
    brokerage: Optional[Decimal] = Field(default=None)
    stamp_duty: Optional[Decimal] = Field(default=None)
    exchange_fee: Optional[Decimal] = Field(default=None)
    gst: Optional[Decimal] = Field(default=None)
    other_fees: Optional[Decimal] = Field(default=None)
    settlement_date: Optional[datetime] = None
    net_cost: Optional[Decimal] = None
    gross_cost: Optional[Decimal] = None
    realized_gain_loss: Optional[Decimal] = None
    transaction_fx_rate: Optional[Decimal] = None
    net_cost_local: Optional[Decimal] = None
    realized_gain_loss_local: Optional[Decimal] = None
    economic_event_id: Optional[str] = None
    linked_transaction_group_id: Optional[str] = None
    calculation_policy_id: Optional[str] = None
    calculation_policy_version: Optional[str] = None
    source_system: Optional[str] = None
    cash_entry_mode: Optional[str] = None
    external_cash_transaction_id: Optional[str] = None
    settlement_cash_account_id: Optional[str] = None
    settlement_cash_instrument_id: Optional[str] = None
    movement_direction: Optional[str] = None
    originating_transaction_id: Optional[str] = None
    originating_transaction_type: Optional[str] = None
    adjustment_reason: Optional[str] = None
    link_type: Optional[str] = None
    reconciliation_key: Optional[str] = None
    interest_direction: Optional[str] = None
    withholding_tax_amount: Optional[Decimal] = None
    other_interest_deductions_amount: Optional[Decimal] = None
    net_interest_amount: Optional[Decimal] = None
    parent_transaction_reference: Optional[str] = None
    linked_parent_event_id: Optional[str] = None
    parent_event_reference: Optional[str] = None
    child_role: Optional[str] = None
    child_sequence_hint: Optional[int] = None
    dependency_reference_ids: Optional[list[str]] = None
    source_instrument_id: Optional[str] = None
    target_instrument_id: Optional[str] = None
    source_transaction_reference: Optional[str] = None
    target_transaction_reference: Optional[str] = None
    linked_cash_transaction_id: Optional[str] = None
    has_synthetic_flow: Optional[bool] = None
    synthetic_flow_effective_date: Optional[date] = None
    synthetic_flow_amount_local: Optional[Decimal] = None
    synthetic_flow_currency: Optional[str] = None
    synthetic_flow_amount_base: Optional[Decimal] = None
    synthetic_flow_fx_rate_to_base: Optional[Decimal] = None
    synthetic_flow_price_used: Optional[Decimal] = None
    synthetic_flow_quantity_used: Optional[Decimal] = None
    synthetic_flow_valuation_method: Optional[str] = None
    synthetic_flow_classification: Optional[str] = None
    synthetic_flow_price_source: Optional[str] = None
    synthetic_flow_fx_source: Optional[str] = None
    synthetic_flow_source: Optional[str] = None
    created_at: Optional[datetime] = None
    epoch: Optional[int] = None


def transaction_event_ordering_key(
    event: "TransactionEvent",
) -> tuple[date, datetime, int, int, str, datetime, str]:
    """
    Deterministic intra-partition ordering for transaction processing.
    Priority:
    1) effective business date (derived from transaction_date)
    2) transaction timestamp
    3) Bundle A dependency rank (source-out, target-in, cash-consideration, other)
    4) Bundle A target leg sequence (child_sequence_hint fallback)
    5) Bundle A target instrument fallback
    6) ingestion timestamp (created_at when present)
    7) stable event identity (transaction_id)
    """
    ingestion_ts = event.created_at or datetime.fromtimestamp(0, tz=timezone.utc)
    target_sequence, target_instrument = ca_bundle_a_target_order_key(event)
    return (
        event.transaction_date.date(),
        event.transaction_date,
        ca_bundle_a_dependency_rank(event),
        target_sequence,
        target_instrument,
        ingestion_ts,
        event.transaction_id,
    )


class DailyPositionSnapshotPersistedEvent(BaseModel):
    """
    Event published after a daily position snapshot has been created or updated.
    This is the definitive trigger for time series generation.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    portfolio_id: str
    security_id: str
    date: date
    epoch: int


class CashflowCalculatedEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cashflow_id: int = Field(...)
    transaction_id: str
    portfolio_id: str
    security_id: Optional[str] = None
    cashflow_date: date
    epoch: Optional[int] = None
    amount: Decimal
    currency: str
    classification: str
    timing: str
    is_position_flow: bool
    is_portfolio_flow: bool
    calculation_type: str = Field(...)


class PositionTimeseriesGeneratedEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    portfolio_id: str
    security_id: str
    date: date


class PortfolioTimeseriesGeneratedEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    portfolio_id: str
    date: date


class PortfolioAggregationRequiredEvent(BaseModel):
    """
    Event published by the AggregationScheduler to trigger a portfolio
    time series calculation for a specific portfolio and date.
    """

    model_config = ConfigDict(from_attributes=True)

    portfolio_id: str
    aggregation_date: date
    correlation_id: Optional[str] = None


class PortfolioValuationRequiredEvent(BaseModel):
    """
    Event published by the ValuationScheduler to trigger a position valuation
    for a specific portfolio, security, and date.
    """

    model_config = ConfigDict(from_attributes=True)

    portfolio_id: str
    security_id: str
    valuation_date: date
    epoch: int
    correlation_id: Optional[str] = None


class TransactionProcessingCompletedEvent(BaseModel):
    """
    Stage-gate event emitted when transaction processing prerequisites are satisfied.
    Current prerequisite pair:
    - processed transaction record is available
    - cashflow calculation record is available
    """

    model_config = ConfigDict(from_attributes=True)

    transaction_id: str
    portfolio_id: str
    security_id: Optional[str] = None
    business_date: date
    epoch: int = 0
    cost_event_seen: bool = True
    cashflow_event_seen: bool = True
    stage_name: str = "TRANSACTION_PROCESSING"
    readiness_reason: str = "cost_and_cashflow_completed"
    correlation_id: Optional[str] = None
