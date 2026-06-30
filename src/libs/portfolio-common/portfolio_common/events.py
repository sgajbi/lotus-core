# libs/portfolio-common/portfolio_common/events.py
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .ca_bundle_a_ordering import (
    ca_bundle_a_dependency_rank,
    ca_bundle_a_target_order_key,
)
from .control_code_normalization import (
    normalize_optional_transaction_control_code,
    normalize_transaction_control_code,
)
from .cost_basis import CostBasisMethod, normalize_cost_basis_method
from .currency_codes import normalize_currency_code, normalize_optional_currency_code
from .decimal_amounts import decimal_or_none
from .transaction_fee_components import (
    TRANSACTION_FEE_COMPONENT_FIELDS,
    resolve_transaction_trade_fee,
)


def _standardize_event_datetime_value(value: object) -> object:
    if value is None:
        return value
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _aware_event_datetime(value: datetime) -> datetime:
    normalized = _standardize_event_datetime_value(value)
    if not isinstance(normalized, datetime):
        raise TypeError("Expected datetime value.")
    return normalized


def _event_decimal_amount(value: object) -> Decimal:
    amount = decimal_or_none(value)
    if amount is None:
        raise ValueError("Amount must be numeric.")
    return amount


class CoreEventModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    event_type: Optional[str] = Field(None)
    schema_version: Optional[str] = Field(None)
    correlation_id: Optional[str] = Field(None)


GOVERNED_EVENT_SCHEMA_FIELDS = frozenset({"event_type", "schema_version"})
GOVERNED_EVENT_ENVELOPE_FIELDS = frozenset({*GOVERNED_EVENT_SCHEMA_FIELDS, "correlation_id"})


def event_business_payload(
    event: BaseModel,
    *,
    include_correlation_id: bool = False,
    mode: str = "python",
) -> dict[str, Any]:
    exclude = set(GOVERNED_EVENT_SCHEMA_FIELDS)
    if not include_correlation_id:
        exclude.add("correlation_id")
    return event.model_dump(mode=mode, exclude=exclude)


class BusinessDateEvent(CoreEventModel):
    """Event model for a raw business date."""

    business_date: date = Field(...)
    calendar_code: str = Field("GLOBAL")
    market_code: Optional[str] = Field(None)
    source_system: Optional[str] = Field(None)
    source_batch_id: Optional[str] = Field(None)


class PortfolioEvent(CoreEventModel):
    """
    Event model for raw portfolio data.
    """

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
    cost_basis_method: Optional[CostBasisMethod] = Field(CostBasisMethod.FIFO)

    @field_validator("cost_basis_method", mode="before")
    @classmethod
    def _normalize_cost_basis_method(cls, value: object) -> CostBasisMethod:
        return normalize_cost_basis_method(value)

    @field_validator("base_currency", mode="before")
    @classmethod
    def _normalize_base_currency(cls, value: object) -> str:
        return normalize_currency_code(value)


class FxRateEvent(CoreEventModel):
    from_currency: str = Field(...)
    to_currency: str = Field(...)
    rate_date: date = Field(...)
    rate: Decimal

    @field_validator("rate")
    @classmethod
    def _validate_positive_rate(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError("FX rate must be greater than zero.")
        return value

    @field_validator("from_currency", "to_currency", mode="before")
    @classmethod
    def _normalize_currency_code(cls, value: object) -> str:
        return normalize_currency_code(value)


class MarketPriceEvent(CoreEventModel):
    security_id: str = Field(...)
    price_date: date = Field(...)
    price: Decimal
    currency: str

    @field_validator("price")
    @classmethod
    def _validate_positive_price(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError("Market price must be greater than zero.")
        return value

    @field_validator("currency", mode="before")
    @classmethod
    def _normalize_currency_code(cls, value: object) -> str:
        return normalize_currency_code(value)


class MarketPricePersistedEvent(CoreEventModel):
    """
    Event published after a market price has been successfully persisted.
    """

    security_id: str
    price_date: date
    price: Decimal
    currency: str

    @field_validator("price")
    @classmethod
    def _validate_positive_price(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError("Market price must be greater than zero.")
        return value

    @field_validator("currency", mode="before")
    @classmethod
    def _normalize_currency_code(cls, value: object) -> str:
        return normalize_currency_code(value)


class InstrumentEvent(CoreEventModel):
    security_id: str = Field(...)
    name: str
    isin: str
    currency: str = Field(...)
    product_type: str = Field(...)
    asset_class: Optional[str] = Field(None)
    portfolio_id: Optional[str] = Field(None)
    trade_date: Optional[date] = Field(None)
    pair_base_currency: Optional[str] = Field(None)
    pair_quote_currency: Optional[str] = Field(None)
    buy_currency: Optional[str] = Field(None)
    sell_currency: Optional[str] = Field(None)
    buy_amount: Optional[Decimal] = Field(None)
    sell_amount: Optional[Decimal] = Field(None)
    contract_rate: Optional[Decimal] = Field(None)
    sector: Optional[str] = None
    country_of_risk: Optional[str] = Field(None)
    rating: Optional[str] = None
    liquidity_tier: Optional[str] = Field(None)
    maturity_date: Optional[date] = Field(None)
    issuer_id: Optional[str] = Field(None)
    issuer_name: Optional[str] = Field(None)
    ultimate_parent_issuer_id: Optional[str] = Field(None)
    ultimate_parent_issuer_name: Optional[str] = Field(None)

    @field_validator(
        "currency",
        "pair_base_currency",
        "pair_quote_currency",
        "buy_currency",
        "sell_currency",
        mode="before",
    )
    @classmethod
    def _normalize_currency_code(cls, value: object) -> str | None:
        return normalize_optional_currency_code(value)


class TransactionEvent(CoreEventModel):
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
    component_type: Optional[str] = None
    component_id: Optional[str] = None
    linked_component_ids: Optional[list[str]] = None
    fx_cash_leg_role: Optional[str] = None
    linked_fx_cash_leg_id: Optional[str] = None
    settlement_status: Optional[str] = None
    pair_base_currency: Optional[str] = None
    pair_quote_currency: Optional[str] = None
    fx_rate_quote_convention: Optional[str] = None
    buy_currency: Optional[str] = None
    sell_currency: Optional[str] = None
    buy_amount: Optional[Decimal] = None
    sell_amount: Optional[Decimal] = None
    contract_rate: Optional[Decimal] = None
    fx_contract_id: Optional[str] = None
    fx_contract_open_transaction_id: Optional[str] = None
    fx_contract_close_transaction_id: Optional[str] = None
    settlement_of_fx_contract_id: Optional[str] = None
    swap_event_id: Optional[str] = None
    near_leg_group_id: Optional[str] = None
    far_leg_group_id: Optional[str] = None
    spot_exposure_model: Optional[str] = None
    fx_realized_pnl_mode: Optional[str] = None
    realized_capital_pnl_local: Optional[Decimal] = None
    realized_fx_pnl_local: Optional[Decimal] = None
    realized_total_pnl_local: Optional[Decimal] = None
    realized_capital_pnl_base: Optional[Decimal] = None
    realized_fx_pnl_base: Optional[Decimal] = None
    realized_total_pnl_base: Optional[Decimal] = None
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

    @field_validator(
        "trade_currency",
        "currency",
        "pair_base_currency",
        "pair_quote_currency",
        "buy_currency",
        "sell_currency",
        "synthetic_flow_currency",
        mode="before",
    )
    @classmethod
    def _normalize_currency_code(cls, value: object) -> str | None:
        return normalize_optional_currency_code(value)

    @field_validator("transaction_type", mode="before")
    @classmethod
    def _normalize_transaction_control_code(cls, value: str | None) -> str:
        return normalize_transaction_control_code(value)

    @field_validator("transaction_date", "settlement_date", "created_at", mode="before")
    @classmethod
    def _standardize_event_datetime(cls, value: object) -> object:
        return _standardize_event_datetime_value(value)

    @field_validator(
        "cash_entry_mode",
        "movement_direction",
        "originating_transaction_type",
        "adjustment_reason",
        "link_type",
        "interest_direction",
        "component_type",
        "fx_cash_leg_role",
        "settlement_status",
        "fx_rate_quote_convention",
        "spot_exposure_model",
        "fx_realized_pnl_mode",
        "child_role",
        "synthetic_flow_valuation_method",
        "synthetic_flow_classification",
        "synthetic_flow_price_source",
        "synthetic_flow_fx_source",
        "synthetic_flow_source",
        mode="before",
    )
    @classmethod
    def _normalize_optional_transaction_control_code(cls, value: str | None) -> str | None:
        return normalize_optional_transaction_control_code(value)

    @field_validator(
        "quantity",
        "price",
        "gross_transaction_amount",
        "withholding_tax_amount",
        "other_interest_deductions_amount",
        "net_interest_amount",
        "synthetic_flow_price_used",
        "synthetic_flow_quantity_used",
    )
    @classmethod
    def _validate_nonnegative_transaction_amount(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and _event_decimal_amount(value) < 0:
            raise ValueError("Amount must be greater than or equal to zero.")
        return value

    @field_validator(
        "transaction_fx_rate",
        "buy_amount",
        "sell_amount",
        "contract_rate",
        "synthetic_flow_fx_rate_to_base",
    )
    @classmethod
    def _validate_positive_transaction_amount(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and _event_decimal_amount(value) <= 0:
            raise ValueError("Amount must be greater than zero.")
        return value

    @model_validator(mode="after")
    def _aggregate_fee_components(self) -> "TransactionEvent":
        self.trade_fee = resolve_transaction_trade_fee(
            self.trade_fee,
            {field: getattr(self, field) for field in TRANSACTION_FEE_COMPONENT_FIELDS},
        )
        return self


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
    transaction_ts = _aware_event_datetime(event.transaction_date)
    ingestion_ts = (
        _aware_event_datetime(event.created_at)
        if event.created_at is not None
        else datetime.fromtimestamp(0, tz=timezone.utc)
    )
    target_sequence, target_instrument = ca_bundle_a_target_order_key(event)
    return (
        transaction_ts.date(),
        transaction_ts,
        ca_bundle_a_dependency_rank(event),
        target_sequence,
        target_instrument,
        ingestion_ts,
        event.transaction_id,
    )


class DailyPositionSnapshotPersistedEvent(CoreEventModel):
    """
    Event published after a daily position snapshot has been created or updated.
    This is the definitive trigger for time series generation.
    """

    id: int
    portfolio_id: str
    security_id: str
    date: date
    epoch: int


class CashflowCalculatedEvent(CoreEventModel):
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


class PositionTimeseriesGeneratedEvent(CoreEventModel):
    portfolio_id: str
    security_id: str
    date: date


class PortfolioTimeseriesGeneratedEvent(CoreEventModel):
    portfolio_id: str
    date: date


class PortfolioAggregationRequiredEvent(CoreEventModel):
    """
    Event published by the AggregationScheduler to trigger a portfolio
    time series calculation for a specific portfolio and date.
    """

    portfolio_id: str
    aggregation_date: date
    correlation_id: Optional[str] = None


class PortfolioValuationRequiredEvent(CoreEventModel):
    """
    Event published by the ValuationScheduler to trigger a position valuation
    for a specific portfolio, security, and date.
    """

    portfolio_id: str
    security_id: str
    valuation_date: date
    epoch: int
    correlation_id: Optional[str] = None


class TransactionProcessingCompletedEvent(CoreEventModel):
    """
    Stage-gate event emitted when transaction processing prerequisites are satisfied.
    Current prerequisite pair:
    - processed transaction record is available
    - cashflow calculation record is available, or the transaction-domain policy marks
      the concrete processing type as non-cashflow
    """

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


class PortfolioDayReadyForValuationEvent(CoreEventModel):
    """
    Stage-gate event emitted when a portfolio-security business day is ready
    for valuation scheduling.
    """

    portfolio_id: str
    security_id: str
    valuation_date: date
    epoch: int = 0
    readiness_reason: str = "transaction_processing.ready"
    correlation_id: Optional[str] = None


class ValuationDayCompletedEvent(CoreEventModel):
    """
    Stage-gate completion event emitted after valuation persistence for a
    portfolio-security business day.
    """

    daily_position_snapshot_id: int
    portfolio_id: str
    security_id: str
    valuation_date: date
    epoch: int = 0
    valuation_status: Optional[str] = None
    correlation_id: Optional[str] = None


class PositionTimeseriesDayCompletedEvent(CoreEventModel):
    """
    Completion event emitted once position-timeseries persistence is complete
    for a portfolio-security business day.
    """

    portfolio_id: str
    security_id: str
    timeseries_date: date
    epoch: int = 0
    correlation_id: Optional[str] = None


class PortfolioAggregationDayCompletedEvent(CoreEventModel):
    """
    Completion event emitted when portfolio aggregation is complete for a
    portfolio business day.
    """

    portfolio_id: str
    aggregation_date: date
    epoch: int = 0
    correlation_id: Optional[str] = None


class FinancialReconciliationRequestedEvent(CoreEventModel):
    """
    Control-plane event emitted when a portfolio-day is ready for automated
    reconciliation execution.
    """

    portfolio_id: str
    business_date: date
    epoch: int = 0
    reconciliation_types: list[str] = Field(
        default_factory=lambda: [
            "transaction_cashflow",
            "position_valuation",
            "timeseries_integrity",
        ]
    )
    requested_by: str = "system_pipeline"
    trigger_stage: str = "portfolio_day.aggregation.completed"
    correlation_id: Optional[str] = None


class FinancialReconciliationCompletedEvent(CoreEventModel):
    """
    Outcome event emitted after an automatic portfolio-day reconciliation bundle
    finishes. The outcome is deterministic and replay-safe for a given
    `(portfolio_id, business_date, epoch)` scope.
    """

    portfolio_id: str
    business_date: date
    epoch: int = 0
    outcome_status: str
    reconciliation_types: list[str]
    blocking_reconciliation_types: list[str] = Field(default_factory=list)
    run_ids: dict[str, str] = Field(default_factory=dict)
    error_count: int = 0
    warning_count: int = 0
    requested_by: str = "system_pipeline"
    trigger_stage: str = "portfolio_day.aggregation.completed"
    correlation_id: Optional[str] = None


class PortfolioDayControlsEvaluatedEvent(CoreEventModel):
    """
    Canonical orchestrator-owned control-stage outcome for a portfolio business day.
    """

    portfolio_id: str
    business_date: date
    epoch: int = 0
    stage_name: str = "FINANCIAL_RECONCILIATION"
    status: str
    controls_blocking: bool = False
    publish_allowed: bool = True
    blocking_reconciliation_types: list[str] = Field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0
    source_event_type: str = "portfolio_day.reconciliation.completed"
    correlation_id: Optional[str] = None
