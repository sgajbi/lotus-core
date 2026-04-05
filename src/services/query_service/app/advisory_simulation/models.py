"""
FILE: src/core/models.py
"""

from decimal import Decimal
from enum import Enum
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_serializer, field_validator, model_validator


class ValuationMode(str, Enum):
    CALCULATED = "CALCULATED"
    TRUST_SNAPSHOT = "TRUST_SNAPSHOT"


class TargetMethod(str, Enum):
    HEURISTIC = "HEURISTIC"
    SOLVER = "SOLVER"


def _quantize_ratio(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"))


_GROUP_CONSTRAINT_KEY_FORMAT = "<attribute_key>:<attribute_value>"


def _is_python_float(candidate: object) -> bool:
    type_name = candidate.__class__.__name__
    if type_name == "float":
        return True
    return False


def _validate_group_constraint_keys(
    group_constraints: Dict[str, "GroupConstraint"],
) -> Dict[str, "GroupConstraint"]:
    for key in group_constraints:
        if key.count(":") != 1:
            raise ValueError(
                f"group_constraints keys must use format '{_GROUP_CONSTRAINT_KEY_FORMAT}'"
            )
        attribute_key, attribute_value = key.split(":", 1)
        if not attribute_key or not attribute_value:
            raise ValueError(
                f"group_constraints keys must use format '{_GROUP_CONSTRAINT_KEY_FORMAT}'"
            )
    return group_constraints


def _validate_optional_ratio_between_zero_and_one(
    value: Optional[Decimal], *, field_name: str
) -> Optional[Decimal]:
    if value is None:
        return value
    if value < Decimal("0") or value > Decimal("1"):
        raise ValueError(f"{field_name} must be between 0 and 1 inclusive")
    return value


def _validate_non_negative_amounts_by_currency(
    amounts_by_currency: Dict[str, Decimal], *, field_name: str
) -> Dict[str, Decimal]:
    for currency, amount in amounts_by_currency.items():
        if not currency:
            raise ValueError(f"{field_name} keys must be non-empty currency codes")
        if amount < Decimal("0"):
            raise ValueError(f"{field_name} values must be non-negative")
    return amounts_by_currency


class Money(BaseModel):
    amount: Decimal = Field(
        description="Monetary amount as decimal string/number.",
        examples=["1000.50"],
    )
    currency: str = Field(
        description="ISO currency code (for example USD, SGD).",
        examples=["USD"],
    )


class FxRate(BaseModel):
    pair: str = Field(
        description="Currency pair in BASE/QUOTE style used by engine lookup.",
        examples=["USD/SGD"],
    )
    rate: Decimal = Field(description="FX conversion rate for the pair.", examples=["1.35"])


class Position(BaseModel):
    instrument_id: str = Field(description="Unique instrument identifier.", examples=["AAPL"])
    quantity: Decimal = Field(description="Held quantity before simulation.", examples=["100"])
    market_value: Optional[Money] = Field(
        default=None,
        description="Optional trusted market value used when valuation_mode=TRUST_SNAPSHOT.",
    )
    lots: List["TaxLot"] = Field(
        default_factory=list,
        description="Optional tax-lot breakdown for tax-aware sell allocation.",
    )

    @model_validator(mode="after")
    def validate_lot_quantity_total(self) -> "Position":
        if not self.lots:
            return self
        total = sum((lot.quantity for lot in self.lots), Decimal("0"))
        if abs(total - self.quantity) > Decimal("0.0001"):
            raise ValueError(
                "sum(lot.quantity) must equal position.quantity within tolerance 0.0001"
            )
        return self


class CashBalance(BaseModel):
    currency: str = Field(description="Cash currency code.", examples=["USD"])
    amount: Decimal = Field(
        description="Available cash amount used by current simulation stages.",
        examples=["25000"],
    )
    settled: Optional[Decimal] = Field(
        default=None,
        description="Optional settled cash amount used by settlement-aware ladder.",
    )
    pending: Optional[Decimal] = Field(
        default=None,
        description="Optional pending cash amount for informational reporting.",
    )


class PortfolioSnapshot(BaseModel):
    model_config = {
        "json_schema_extra": {
            "example": {
                "portfolio_id": "pf_1",
                "base_currency": "USD",
                "positions": [{"instrument_id": "AAPL", "quantity": "100"}],
                "cash_balances": [{"currency": "USD", "amount": "5000"}],
            }
        }
    }

    snapshot_id: Optional[str] = Field(
        default=None,
        description="Optional immutable snapshot identifier for lineage.",
    )
    portfolio_id: str = Field(description="Portfolio identifier.", examples=["pf_123"])
    base_currency: str = Field(
        description="Base reporting currency for valuation and rules.",
        examples=["USD"],
    )
    positions: List[Position] = Field(default_factory=list, description="Current held positions.")
    cash_balances: List[CashBalance] = Field(
        default_factory=list,
        description="Current portfolio cash balances by currency.",
    )


class Price(BaseModel):
    instrument_id: str = Field(
        description="Instrument identifier for the price row.", examples=["AAPL"]
    )
    price: Decimal = Field(
        description="Last/mark price used in valuation and sizing.", examples=["180.25"]
    )
    currency: str = Field(description="Currency of the price.", examples=["USD"])


class MarketDataSnapshot(BaseModel):
    model_config = {
        "json_schema_extra": {
            "example": {
                "prices": [{"instrument_id": "AAPL", "price": "180.25", "currency": "USD"}],
                "fx_rates": [{"pair": "USD/SGD", "rate": "1.35"}],
            }
        }
    }

    snapshot_id: Optional[str] = Field(
        default=None,
        description="Optional immutable market-data snapshot identifier for lineage.",
    )
    prices: List[Price] = Field(default_factory=list, description="Instrument prices.")
    fx_rates: List[FxRate] = Field(
        default_factory=list, description="FX rates for currency conversion."
    )


class ModelTarget(BaseModel):
    instrument_id: str = Field(
        description="Instrument identifier in model target.", examples=["AAPL"]
    )
    weight: Decimal = Field(
        description="Target portfolio weight for the instrument.", examples=["0.25"]
    )


class ModelPortfolio(BaseModel):
    targets: List[ModelTarget] = Field(description="List of model target weights.")


class ReferenceAssetClassTarget(BaseModel):
    asset_class: str = Field(description="Reference model asset-class bucket.")
    weight: Decimal = Field(description="Target weight for the asset-class bucket.")


class ReferenceInstrumentTarget(BaseModel):
    instrument_id: str = Field(description="Reference model instrument identifier.")
    weight: Decimal = Field(description="Target weight for the instrument bucket.")


class ReferenceModel(BaseModel):
    model_id: str = Field(description="Reference model identifier.")
    as_of: str = Field(description="Reference model as-of date.")
    base_currency: str = Field(description="Reference model base currency.")
    asset_class_targets: List[ReferenceAssetClassTarget] = Field(
        default_factory=list,
        description="Reference target weights by asset class.",
    )
    instrument_targets: List[ReferenceInstrumentTarget] = Field(
        default_factory=list,
        description="Optional reference target weights by instrument.",
    )


class TaxLot(BaseModel):
    lot_id: str = Field(
        description="Unique lot identifier within instrument.", examples=["LOT_001"]
    )
    quantity: Decimal = Field(ge=0, description="Lot quantity.", examples=["50"])
    unit_cost: Money = Field(description="Per-unit cost basis for the lot.")
    purchase_date: str = Field(description="Lot purchase date (ISO date string).")


class ShelfEntry(BaseModel):
    instrument_id: str = Field(
        description="Instrument identifier in product shelf.", examples=["AAPL"]
    )
    status: Literal["APPROVED", "RESTRICTED", "BANNED", "SUSPENDED", "SELL_ONLY"]
    asset_class: str = Field(
        default="UNKNOWN", description="Asset-class label for aggregation/reporting."
    )
    issuer_id: Optional[str] = Field(
        default=None,
        description="Issuer identifier used for concentration analytics and suitability checks.",
        examples=["ISSUER_TECH_1"],
    )
    liquidity_tier: Optional[Literal["L1", "L2", "L3", "L4", "L5"]] = Field(
        default=None,
        description="Liquidity tier label used for suitability liquidity exposure checks.",
        examples=["L1", "L4"],
    )
    settlement_days: int = Field(
        default=2,
        ge=0,
        le=10,
        description="Settlement lag in business-day offsets used by settlement ladder.",
    )
    min_notional: Optional[Money] = Field(
        default=None,
        description="Optional per-instrument minimum trade notional.",
    )
    attributes: Dict[str, str] = Field(
        default_factory=dict,
        description="Attribute tags used for group constraints (for example sector, region).",
    )


class GroupConstraint(BaseModel):
    max_weight: Decimal = Field(
        description="Maximum allowed aggregate weight for the tagged group."
    )

    @field_validator("max_weight")
    @classmethod
    def validate_max_weight(cls, v: Decimal) -> Decimal:
        if v < Decimal("0") or v > Decimal("1"):
            raise ValueError("max_weight must be between 0 and 1 inclusive")
        return v


class SuitabilityThresholds(BaseModel):
    single_position_max_weight: Decimal = Field(
        default=Decimal("0.10"),
        ge=0,
        le=1,
        description="Maximum advisory suitability weight per single instrument.",
        examples=["0.10"],
    )
    issuer_max_weight: Decimal = Field(
        default=Decimal("0.20"),
        ge=0,
        le=1,
        description="Maximum advisory suitability aggregate weight per issuer.",
        examples=["0.20"],
    )
    max_weight_by_liquidity_tier: Dict[str, Decimal] = Field(
        default_factory=lambda: {"L4": Decimal("0.10"), "L5": Decimal("0.05")},
        description=(
            "Maximum advisory suitability aggregate weight by liquidity tier, "
            "for example {'L4': '0.10', 'L5': '0.05'}."
        ),
        examples=[{"L4": "0.10", "L5": "0.05"}],
    )
    cash_band_min_weight: Decimal = Field(
        default=Decimal("0.01"),
        ge=0,
        le=1,
        description="Minimum advisory suitability cash weight.",
        examples=["0.01"],
    )
    cash_band_max_weight: Decimal = Field(
        default=Decimal("0.05"),
        ge=0,
        le=1,
        description="Maximum advisory suitability cash weight.",
        examples=["0.05"],
    )
    data_quality_issue_severity: Literal["LOW", "MEDIUM", "HIGH"] = Field(
        default="MEDIUM",
        description="Severity used for suitability data-quality issues.",
        examples=["MEDIUM"],
    )

    @field_validator("max_weight_by_liquidity_tier")
    @classmethod
    def validate_max_weight_by_liquidity_tier(cls, v: Dict[str, Decimal]) -> Dict[str, Decimal]:
        for tier, value in v.items():
            if tier not in {"L1", "L2", "L3", "L4", "L5"}:
                raise ValueError("liquidity tier keys must be one of L1, L2, L3, L4, L5")
            if value < Decimal("0") or value > Decimal("1"):
                raise ValueError("liquidity-tier max weights must be between 0 and 1 inclusive")
        return v

    @model_validator(mode="after")
    def validate_cash_band(self) -> "SuitabilityThresholds":
        if self.cash_band_min_weight > self.cash_band_max_weight:
            raise ValueError("suitability cash band min cannot exceed max")
        return self


class EngineOptions(BaseModel):
    model_config = {
        "json_schema_extra": {
            "example": {
                "target_method": "HEURISTIC",
                "max_turnover_pct": "0.15",
                "enable_tax_awareness": True,
                "max_realized_capital_gains": "100",
                "enable_settlement_awareness": False,
            }
        }
    }

    valuation_mode: ValuationMode = Field(
        default=ValuationMode.CALCULATED,
        description="Valuation source policy.",
        examples=["CALCULATED"],
    )
    target_method: TargetMethod = Field(
        default=TargetMethod.HEURISTIC,
        description="Stage-3 target generation method.",
        examples=["HEURISTIC"],
    )
    compare_target_methods: bool = Field(
        default=False,
        description="Run both target methods and include divergence diagnostics.",
        examples=[False],
    )
    compare_target_methods_tolerance: Decimal = Field(
        default=Decimal("0.0001"),
        description="Tolerance used when comparing method outputs.",
        examples=["0.0001"],
    )

    cash_band_min_weight: Decimal = Field(
        default=Decimal("0.00"),
        description="Lower soft bound for cash weight.",
        examples=["0.00"],
    )
    cash_band_max_weight: Decimal = Field(
        default=Decimal("1.00"),
        description="Upper soft bound for cash weight.",
        examples=["1.00"],
    )

    single_position_max_weight: Optional[Decimal] = Field(
        default=None,
        description="Hard maximum weight allowed for a single position.",
        examples=["0.30"],
    )
    min_trade_notional: Optional[Money] = Field(
        default=None,
        description="Request-level minimum trade notional threshold.",
    )

    allow_restricted: bool = Field(
        default=False,
        description="Allow buys in RESTRICTED shelf instruments.",
        examples=[False],
    )
    suppress_dust_trades: bool = Field(
        default=True,
        description="Suppress trades under minimum notional threshold.",
        examples=[True],
    )
    dust_trade_threshold: Optional[Money] = Field(
        default=None,
        description="Reserved field; currently not consumed by engine logic.",
    )
    fx_buffer_pct: Decimal = Field(
        default=Decimal("0.01"),
        description="Buffer applied when generating FX funding intents.",
        examples=["0.01"],
    )
    block_on_missing_prices: bool = Field(
        default=True,
        description="Block run when required prices are missing.",
        examples=[True],
    )
    block_on_missing_fx: bool = Field(
        default=True,
        description="Block run when required FX rates are missing.",
        examples=[True],
    )
    min_cash_buffer_pct: Decimal = Field(
        default=Decimal("0.0"),
        description="Minimum cash buffer preserved during target generation.",
        examples=["0.05"],
    )
    max_turnover_pct: Optional[Decimal] = Field(
        default=None,
        description="Optional turnover cap as percentage of portfolio value.",
        examples=["0.15"],
    )
    enable_tax_awareness: bool = Field(
        default=False,
        description="Enable tax-aware lot-based sell allocation.",
        examples=[True],
    )
    max_realized_capital_gains: Optional[Decimal] = Field(
        default=None,
        ge=0,
        description="Optional run-level realized capital gains budget in base currency.",
        examples=["100"],
    )
    enable_settlement_awareness: bool = Field(
        default=False,
        description="Enable settlement-time cash ladder overdraft checks.",
        examples=[True],
    )
    enable_proposal_simulation: bool = Field(
        default=False,
        description="Enable advisory proposal simulation endpoint behavior.",
        examples=[False],
    )
    enable_workflow_gates: bool = Field(
        default=True,
        description="Enable deterministic workflow gate decision output.",
        examples=[True],
    )
    workflow_requires_client_consent: bool = Field(
        default=False,
        description=(
            "Require client consent before execution in gate-decision policy. "
            "Typically true for advisory and false for discretionary mandates."
        ),
        examples=[False],
    )
    client_consent_already_obtained: bool = Field(
        default=False,
        description=(
            "Signals that client consent has already been obtained, allowing "
            "gate progression to execution-ready when policy permits."
        ),
        examples=[False],
    )
    proposal_apply_cash_flows_first: bool = Field(
        default=True,
        description="Apply proposal cash flows before manual trade simulation.",
        examples=[True],
    )
    proposal_block_negative_cash: bool = Field(
        default=True,
        description="Block proposal when cash-flow withdrawals create negative balances.",
        examples=[True],
    )
    link_buy_to_same_currency_sell_dependency: Optional[bool] = Field(
        default=None,
        description=(
            "Attach BUY intent dependency to a same-currency SELL intent. "
            "When null, advisory runtime keeps the default disabled unless explicitly enabled."
        ),
        examples=[None, True, False],
    )
    enable_drift_analytics: bool = Field(
        default=True,
        description="Enable advisory drift analytics when a reference model is provided.",
        examples=[True],
    )
    enable_suitability_scanner: bool = Field(
        default=True,
        description="Enable advisory suitability scanner output in proposal simulation results.",
        examples=[True],
    )
    suitability_thresholds: SuitabilityThresholds = Field(
        default_factory=SuitabilityThresholds,
        description="Threshold settings used by advisory suitability scanner checks.",
    )
    enable_instrument_drift: bool = Field(
        default=True,
        description="Enable instrument-level drift analytics when reference targets are present.",
        examples=[True],
    )
    drift_top_contributors_limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum bucket count in top-contributor and highlight lists.",
        examples=[5],
    )
    drift_unmodeled_exposure_threshold: Decimal = Field(
        default=Decimal("0.01"),
        ge=0,
        le=1,
        description="Minimum exposure threshold for unmodeled-exposure highlights.",
        examples=["0.01"],
    )
    auto_funding: bool = Field(
        default=True,
        description="Enable advisory auto-funding for foreign-currency proposal buys.",
        examples=[True],
    )
    funding_mode: Literal["AUTO_FX"] = Field(
        default="AUTO_FX",
        description="Advisory proposal funding mode.",
        examples=["AUTO_FX"],
    )
    fx_funding_source_currency: Literal["BASE_ONLY", "ANY_CASH"] = Field(
        default="ANY_CASH",
        description="Funding source selection policy for generated advisory FX intents.",
        examples=["ANY_CASH"],
    )
    fx_generation_policy: Literal["ONE_FX_PER_CCY"] = Field(
        default="ONE_FX_PER_CCY",
        description="FX intent generation policy for advisory auto-funding.",
        examples=["ONE_FX_PER_CCY"],
    )
    settlement_horizon_days: int = Field(
        default=5,
        ge=0,
        le=10,
        description="Settlement ladder horizon in day offsets from T+0.",
        examples=[5],
    )
    fx_settlement_days: int = Field(
        default=2,
        ge=0,
        le=10,
        description="Settlement lag used for generated FX intents.",
        examples=[2],
    )
    max_overdraft_by_ccy: Dict[str, Decimal] = Field(
        default_factory=dict,
        description="Optional overdraft allowance by currency for settlement ladder.",
        examples=[{"USD": "1000"}],
    )

    # Key format: "<attribute_key>:<attribute_value>", for example "sector:TECH"
    group_constraints: Dict[str, GroupConstraint] = Field(
        default_factory=dict,
        description="Group constraint map keyed by '<attribute_key>:<attribute_value>'.",
        examples=[{"sector:TECH": {"max_weight": "0.25"}}],
    )

    @field_validator("group_constraints")
    @classmethod
    def validate_group_constraint_keys(
        cls, v: Dict[str, GroupConstraint]
    ) -> Dict[str, GroupConstraint]:
        return _validate_group_constraint_keys(v)

    @field_validator("max_turnover_pct")
    @classmethod
    def validate_max_turnover_pct(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        return _validate_optional_ratio_between_zero_and_one(v, field_name="max_turnover_pct")

    @field_validator("max_overdraft_by_ccy")
    @classmethod
    def validate_max_overdraft_by_ccy(cls, v: Dict[str, Decimal]) -> Dict[str, Decimal]:
        return _validate_non_negative_amounts_by_currency(v, field_name="max_overdraft_by_ccy")


class AllocationMetric(BaseModel):
    key: str = Field(description="Allocation bucket key (instrument, asset class, or tag value).")
    weight: Decimal = Field(description="Weight of the bucket in portfolio total value.")
    value: Money = Field(description="Monetary value of the bucket.")

    @field_serializer("weight")
    def serialize_weight(self, value: Decimal) -> Decimal:
        return _quantize_ratio(value)


class PositionSummary(BaseModel):
    instrument_id: str = Field(description="Instrument identifier.")
    quantity: Decimal = Field(description="Simulated quantity.")
    instrument_currency: str = Field(description="Instrument trading currency.")
    asset_class: str = Field(default="UNKNOWN", description="Asset-class label for aggregation.")
    price: Optional[Money] = Field(default=None, description="Price used in valuation.")
    value_in_instrument_ccy: Money = Field(description="Position value in instrument currency.")
    value_in_base_ccy: Money = Field(description="Position value converted to base currency.")
    weight: Decimal = Field(description="Portfolio weight in base currency terms.")

    @field_serializer("weight")
    def serialize_weight(self, value: Decimal) -> Decimal:
        return _quantize_ratio(value)


class SimulatedState(BaseModel):
    total_value: Money = Field(description="Total simulated portfolio value in base currency.")
    cash_balances: List[CashBalance] = Field(
        default_factory=list, description="Cash balances by currency."
    )
    positions: List[PositionSummary] = Field(
        default_factory=list, description="Position-level simulated state."
    )
    allocation_by_asset_class: List[AllocationMetric] = Field(
        default_factory=list,
        description="Allocation grouped by asset class plus CASH bucket.",
    )
    allocation_by_instrument: List[AllocationMetric] = Field(
        default_factory=list,
        description="Allocation grouped by instrument id.",
    )
    allocation: List[AllocationMetric] = Field(
        default_factory=list,
        description="Legacy allocation view, aligned to allocation_by_instrument.",
    )
    allocation_by_attribute: Dict[str, List[AllocationMetric]] = Field(
        default_factory=dict,
        description="Allocation grouped by configured shelf attributes.",
    )


class ExcludedInstrument(BaseModel):
    instrument_id: str = Field(description="Instrument excluded from buy/sell universe.")
    reason_code: str = Field(description="Reason code for exclusion.")
    details: Optional[str] = Field(
        default=None, description="Optional details for exclusion reason."
    )


class UniverseCoverage(BaseModel):
    price_coverage_pct: Decimal = Field(
        description="Price coverage percentage for required instruments."
    )
    fx_coverage_pct: Decimal = Field(
        description="FX coverage percentage for required currency pairs."
    )


class UniverseData(BaseModel):
    universe_id: str = Field(description="Universe identifier for the run.")
    eligible_for_buy: List[str] = Field(
        default_factory=list, description="Instrument ids eligible for buy intents."
    )
    eligible_for_sell: List[str] = Field(
        default_factory=list,
        description="Instrument ids eligible for sell intents.",
    )
    excluded: List[ExcludedInstrument] = Field(
        default_factory=list,
        description="Instruments excluded by shelf/data constraints.",
    )
    coverage: UniverseCoverage = Field(description="Market-data coverage metrics.")


class TargetInstrument(BaseModel):
    model_config = {"protected_namespaces": ()}
    instrument_id: str = Field(description="Instrument identifier in target trace.")
    model_weight: Decimal = Field(description="Input model weight.")
    final_weight: Decimal = Field(description="Final constrained target weight.")
    final_value: Money = Field(description="Final constrained target value in base currency.")
    tags: List[str] = Field(
        default_factory=list, description="Trace tags explaining target adjustments."
    )


class TargetData(BaseModel):
    target_id: str = Field(description="Target stage identifier.")
    strategy: Dict[str, Any] = Field(description="Strategy metadata (currently minimal).")
    targets: List[TargetInstrument] = Field(description="Instrument-level target trace output.")


class IntentRationale(BaseModel):
    code: str = Field(description="Short rationale code for generated intent.")
    message: str = Field(description="Human-readable rationale message.")


class SecurityTradeIntent(BaseModel):
    intent_type: Literal["SECURITY_TRADE"] = Field(
        default="SECURITY_TRADE",
        description="Intent discriminator.",
    )
    intent_id: str = Field(description="Intent identifier unique within run.")
    instrument_id: str = Field(description="Instrument identifier for trade.")
    side: Literal["BUY", "SELL"] = Field(description="Trade side.")
    quantity: Optional[Decimal] = Field(default=None, description="Trade quantity.")
    notional: Optional[Money] = Field(
        default=None, description="Trade notional in instrument currency."
    )
    notional_base: Optional[Money] = Field(
        default=None, description="Trade notional converted to base currency."
    )
    dependencies: List[str] = Field(
        default_factory=list, description="Intent ids that must execute first."
    )
    rationale: Optional[IntentRationale] = Field(
        default=None, description="Rationale for this intent."
    )
    constraints_applied: List[str] = Field(
        default_factory=list,
        description="Constraint labels applied during sizing.",
    )


class FxSpotIntent(BaseModel):
    intent_type: Literal["FX_SPOT"] = Field(default="FX_SPOT", description="Intent discriminator.")
    intent_id: str = Field(description="Intent identifier unique within run.")
    pair: str = Field(description="FX pair of the conversion intent.")
    buy_currency: str = Field(description="Currency bought by this FX trade.")
    buy_amount: Decimal = Field(description="Estimated amount bought.")
    sell_currency: str = Field(description="Currency sold by this FX trade.")
    sell_amount_estimated: Decimal = Field(description="Estimated amount sold.")
    dependencies: List[str] = Field(
        default_factory=list, description="Intent ids that must execute first."
    )
    rationale: Optional[IntentRationale] = Field(
        default=None, description="Rationale for this FX intent."
    )


class CashFlowIntent(BaseModel):
    intent_type: Literal["CASH_FLOW"] = Field(
        default="CASH_FLOW",
        description="Intent discriminator.",
        examples=["CASH_FLOW"],
    )
    intent_id: str = Field(description="Intent identifier unique within run.", examples=["oi_cf_1"])
    currency: str = Field(description="Cash-flow currency code.", examples=["USD"])
    amount: Decimal = Field(description="Signed cash-flow amount.", examples=["2000.00"])
    description: Optional[str] = Field(
        default=None,
        description="Optional advisor-entered note.",
        examples=["Client top-up"],
    )


OrderIntent = Union[SecurityTradeIntent, FxSpotIntent]
ProposalOrderIntent = Union[CashFlowIntent, FxSpotIntent, SecurityTradeIntent]


class RuleResult(BaseModel):
    rule_id: str = Field(description="Rule identifier.")
    severity: Literal["HARD", "SOFT", "INFO"] = Field(description="Rule severity tier.")
    status: Literal["PASS", "FAIL"] = Field(description="Rule evaluation outcome.")
    measured: Decimal = Field(description="Measured value used in evaluation.")
    threshold: Dict[str, Decimal] = Field(description="Threshold values applied by the rule.")
    reason_code: str = Field(description="Reason code for rule outcome.")
    remediation_hint: Optional[str] = Field(
        default=None, description="Optional guidance on remediation."
    )


class SuppressedIntent(BaseModel):
    instrument_id: str = Field(description="Instrument id for suppressed trade.")
    reason: str = Field(description="Suppression reason.")
    intended_notional: Money = Field(description="Original intended notional.")
    threshold: Money = Field(description="Suppression threshold that was not met.")


class DroppedIntent(BaseModel):
    instrument_id: str = Field(description="Instrument id for dropped trade under turnover cap.")
    reason: str = Field(description="Drop reason code.")
    potential_notional: Money = Field(description="Potential notional if the trade had been kept.")
    score: Decimal = Field(description="Ranking score used in turnover selection.")


class GroupConstraintEvent(BaseModel):
    constraint_key: str = Field(description="Applied group constraint key.")
    group_weight_before: Decimal = Field(description="Group weight before capping.")
    max_weight: Decimal = Field(description="Configured maximum allowed group weight.")
    released_weight: Decimal = Field(description="Weight released by cap operation.")
    recipients: Dict[str, Decimal] = Field(
        default_factory=dict,
        description="Redistribution recipients and allocated weight shares.",
    )
    status: Literal["CAPPED", "BLOCKED"] = Field(description="Constraint application outcome.")


class TaxBudgetConstraintEvent(BaseModel):
    instrument_id: str = Field(description="Instrument constrained by tax budget.")
    requested_quantity: Decimal = Field(description="Requested sell quantity before budget limit.")
    allowed_quantity: Decimal = Field(description="Allowed sell quantity after budget constraint.")
    reason_code: str = Field(description="Constraint reason code.")


class CashLadderPoint(BaseModel):
    date_offset: int = Field(description="Day offset from T+0.")
    currency: str = Field(description="Currency for projected balance.")
    projected_balance: Decimal = Field(description="Projected cumulative balance on the day.")


class CashLadderBreach(BaseModel):
    date_offset: int = Field(description="Day offset where breach occurs.")
    currency: str = Field(description="Currency where breach occurs.")
    projected_balance: Decimal = Field(description="Projected balance at breach point.")
    allowed_floor: Decimal = Field(description="Configured allowed floor for that currency/day.")
    reason_code: str = Field(description="Breach reason code.")


class FundingPlanEntry(BaseModel):
    target_currency: str = Field(description="Currency required by advisory BUY intents.")
    required: Decimal = Field(description="Total required amount in target currency.")
    available_before_fx: Decimal = Field(
        description="Available amount in target currency before generated FX."
    )
    fx_needed: Decimal = Field(description="Generated FX buy amount needed in target currency.")
    fx_pair: Optional[str] = Field(
        default=None,
        description="Resolved FX pair used for funding, when available.",
    )
    funding_currency: Optional[str] = Field(
        default=None,
        description="Currency sold to fund target-currency buys.",
    )


class InsufficientCashEntry(BaseModel):
    currency: str = Field(description="Currency where funding cash deficit is detected.")
    deficit: Decimal = Field(description="Deficit amount in the funding currency.")


class DiagnosticsData(BaseModel):
    warnings: List[str] = Field(default_factory=list, description="Run-level warning codes.")
    suppressed_intents: List[SuppressedIntent] = Field(
        default_factory=list,
        description="Intents suppressed during generation (for example dust suppression).",
    )
    dropped_intents: List[DroppedIntent] = Field(
        default_factory=list,
        description="Intents dropped by turnover control.",
    )
    group_constraint_events: List[GroupConstraintEvent] = Field(
        default_factory=list,
        description="Group constraint capping/redistribution events.",
    )
    tax_budget_constraint_events: List[TaxBudgetConstraintEvent] = Field(
        default_factory=list,
        description="Tax budget constraint events by instrument.",
    )
    cash_ladder: List[CashLadderPoint] = Field(
        default_factory=list,
        description="Settlement-aware projected cash ladder points.",
    )
    cash_ladder_breaches: List[CashLadderBreach] = Field(
        default_factory=list,
        description="Settlement ladder breaches that trigger blocks.",
    )
    missing_fx_pairs: List[str] = Field(
        default_factory=list,
        description="Missing FX pairs required for generated funding or proposal valuation.",
    )
    funding_plan: List[FundingPlanEntry] = Field(
        default_factory=list,
        description="Advisory funding plan details for generated FX intents.",
    )
    insufficient_cash: List[InsufficientCashEntry] = Field(
        default_factory=list,
        description="Funding deficits that block proposal simulation.",
    )
    data_quality: Dict[str, List[str]] = Field(
        description="Data-quality issue buckets and affected keys."
    )


class LineageData(BaseModel):
    portfolio_snapshot_id: str = Field(description="Portfolio snapshot id used by run.")
    market_data_snapshot_id: str = Field(description="Market-data snapshot id used by run.")
    request_hash: str = Field(description="Request hash/idempotency marker used in lineage.")
    idempotency_key: Optional[str] = Field(
        default=None,
        description="Request idempotency key.",
        examples=["proposal-idem-001"],
    )
    engine_version: Optional[str] = Field(
        default=None,
        description="Engine version identifier.",
        examples=["0.1.0"],
    )
    simulation_contract_version: Optional[str] = Field(
        default=None,
        description="Canonical simulation contract version used for this result.",
        examples=["advisory-simulation.v1"],
    )


class Reconciliation(BaseModel):
    before_total_value: Money = Field(description="Before-state total value.")
    after_total_value: Money = Field(description="After-state total value.")
    delta: Money = Field(description="After minus before.")
    tolerance: Money = Field(description="Allowed reconciliation tolerance.")
    status: Literal["OK", "MISMATCH"] = Field(description="Reconciliation outcome.")


class TaxImpact(BaseModel):
    total_realized_gain: Money = Field(
        description="Aggregate realized gain from constrained sell allocation."
    )
    total_realized_loss: Money = Field(
        description="Aggregate realized loss from constrained sell allocation."
    )
    budget_limit: Optional[Money] = Field(default=None, description="Configured gains budget.")
    budget_used: Optional[Money] = Field(default=None, description="Portion of budget consumed.")


class DriftReferenceModelSummary(BaseModel):
    model_id: str = Field(description="Reference model identifier.")
    as_of: str = Field(description="Reference model as-of date.")
    base_currency: str = Field(description="Reference model base currency.")


class DriftBucketDetail(BaseModel):
    bucket: str = Field(description="Drift bucket key.")
    model_weight: Decimal = Field(description="Reference model weight for the bucket.")
    portfolio_weight_before: Decimal = Field(
        description="Before-state portfolio weight for the bucket."
    )
    portfolio_weight_after: Decimal = Field(
        description="After-state portfolio weight for the bucket."
    )
    drift_before: Decimal = Field(description="Signed before-state drift for the bucket.")
    drift_after: Decimal = Field(description="Signed after-state drift for the bucket.")
    abs_drift_before: Decimal = Field(description="Absolute before-state drift for the bucket.")
    abs_drift_after: Decimal = Field(description="Absolute after-state drift for the bucket.")
    improvement: Decimal = Field(description="Positive when absolute drift improves.")


class DriftDimensionAnalysis(BaseModel):
    drift_total_before: Decimal = Field(description="Total drift in before-state.")
    drift_total_after: Decimal = Field(description="Total drift in after-state.")
    drift_total_delta: Decimal = Field(
        description="After minus before drift total. Negative means improvement."
    )
    top_contributors_before: List[DriftBucketDetail] = Field(
        default_factory=list,
        description="Largest before-state drift contributors.",
    )
    buckets: List[DriftBucketDetail] = Field(
        default_factory=list,
        description="Deterministic drift details for all buckets.",
    )


class DriftHighlightEntry(BaseModel):
    bucket: str = Field(description="Highlighted drift bucket.")
    improvement: Decimal = Field(description="Improvement value for the highlighted bucket.")


class DriftUnmodeledExposure(BaseModel):
    bucket: str = Field(description="Bucket with model weight of zero.")
    portfolio_weight_before: Decimal = Field(description="Before-state exposure for the bucket.")
    portfolio_weight_after: Decimal = Field(description="After-state exposure for the bucket.")
    max_portfolio_weight: Decimal = Field(
        description="Max of before/after exposure for the bucket."
    )


class DriftHighlights(BaseModel):
    largest_improvements: List[DriftHighlightEntry] = Field(
        default_factory=list,
        description="Buckets with largest positive drift improvements.",
    )
    largest_deteriorations: List[DriftHighlightEntry] = Field(
        default_factory=list,
        description="Buckets with largest drift deteriorations.",
    )
    unmodeled_exposures: List[DriftUnmodeledExposure] = Field(
        default_factory=list,
        description="Buckets where model weight is zero and exposure exceeds threshold.",
    )


class DriftAnalysis(BaseModel):
    reference_model: DriftReferenceModelSummary = Field(
        description="Reference model identifier details."
    )
    asset_class: DriftDimensionAnalysis = Field(description="Asset-class drift analytics.")
    instrument: Optional[DriftDimensionAnalysis] = Field(
        default=None,
        description="Instrument drift analytics when instrument targets are provided.",
    )
    highlights: DriftHighlights = Field(description="Deterministic advisory highlights.")


class SuitabilityEvidenceSnapshotIds(BaseModel):
    portfolio_snapshot_id: str = Field(
        description="Portfolio snapshot id used as evidence source.",
        examples=["pf_advisory_01"],
    )
    market_data_snapshot_id: str = Field(
        description="Market-data snapshot id used as evidence source.",
        examples=["md_2026_02_19"],
    )


class SuitabilityEvidence(BaseModel):
    as_of: str = Field(
        description="Suitability evidence as-of identifier derived from request snapshots.",
        examples=["md_2026_02_19"],
    )
    snapshot_ids: SuitabilityEvidenceSnapshotIds = Field(
        description="Snapshot identifiers used by suitability checks."
    )


class SuitabilityIssue(BaseModel):
    issue_id: str = Field(
        description="Stable suitability issue identifier.",
        examples=["SUIT_SINGLE_POSITION_MAX"],
    )
    issue_key: str = Field(
        description="Deterministic issue key used for before/after classification.",
        examples=["SINGLE_POSITION_MAX|US_EQ_ETF"],
    )
    dimension: Literal[
        "CONCENTRATION",
        "ISSUER",
        "LIQUIDITY",
        "GOVERNANCE",
        "CASH",
        "DATA_QUALITY",
    ] = Field(
        description="Suitability issue dimension.",
        examples=["CONCENTRATION"],
    )
    severity: Literal["LOW", "MEDIUM", "HIGH"] = Field(
        description="Advisory suitability severity level.",
        examples=["HIGH"],
    )
    status_change: Literal["NEW", "RESOLVED", "PERSISTENT"] = Field(
        description="Before/after suitability state transition class.",
        examples=["NEW"],
    )
    summary: str = Field(
        description="Short suitability issue narrative.",
        examples=["Single position exceeds 10% cap."],
    )
    details: Dict[str, str] = Field(
        default_factory=dict,
        description="Deterministic suitability measurement details encoded as strings.",
        examples=[
            {
                "threshold": "0.10",
                "measured_before": "0.12",
                "measured_after": "0.09",
                "instrument_id": "US_EQ_ETF",
            }
        ],
    )
    evidence: SuitabilityEvidence = Field(description="Evidence lineage for this issue.")


class SuitabilitySummary(BaseModel):
    new_count: int = Field(description="Count of NEW suitability issues.", examples=[1])
    resolved_count: int = Field(description="Count of RESOLVED suitability issues.", examples=[2])
    persistent_count: int = Field(
        description="Count of PERSISTENT suitability issues.",
        examples=[3],
    )
    highest_severity_new: Optional[Literal["LOW", "MEDIUM", "HIGH"]] = Field(
        default=None,
        description="Highest severity among NEW issues, when present.",
        examples=["HIGH"],
    )


class SuitabilityResult(BaseModel):
    summary: SuitabilitySummary = Field(description="Suitability issue summary counts.")
    issues: List[SuitabilityIssue] = Field(
        default_factory=list,
        description="Deterministic ordered suitability issue list.",
    )
    recommended_gate: Literal["NONE", "RISK_REVIEW", "COMPLIANCE_REVIEW"] = Field(
        description="Advisory gate recommendation derived from NEW issue severities.",
        examples=["COMPLIANCE_REVIEW"],
    )


class GateReason(BaseModel):
    reason_code: str = Field(
        description="Stable workflow reason code.",
        examples=["HARD_RULE_FAIL:INSUFFICIENT_CASH"],
    )
    severity: Literal["LOW", "MEDIUM", "HIGH"] = Field(
        description="Reason severity level used for deterministic ordering.",
        examples=["HIGH"],
    )
    source: Literal["RULE_ENGINE", "SUITABILITY", "DATA_QUALITY"] = Field(
        description="Reason source subsystem.",
        examples=["RULE_ENGINE"],
    )
    details: Dict[str, str] = Field(
        default_factory=dict,
        description="Deterministic structured details for the reason.",
    )


class GateDecisionSummary(BaseModel):
    hard_fail_count: int = Field(description="Count of hard rule failures.", examples=[1])
    soft_fail_count: int = Field(description="Count of soft rule failures.", examples=[0])
    new_high_suitability_count: int = Field(
        description="Count of NEW suitability issues with HIGH severity.",
        examples=[0],
    )
    new_medium_suitability_count: int = Field(
        description="Count of NEW suitability issues with MEDIUM severity.",
        examples=[0],
    )


class GateDecision(BaseModel):
    gate: Literal[
        "BLOCKED",
        "RISK_REVIEW_REQUIRED",
        "COMPLIANCE_REVIEW_REQUIRED",
        "CLIENT_CONSENT_REQUIRED",
        "EXECUTION_READY",
        "NONE",
    ] = Field(
        description="Deterministic workflow gate outcome.",
        examples=["CLIENT_CONSENT_REQUIRED"],
    )
    recommended_next_step: Literal[
        "FIX_INPUT",
        "RISK_REVIEW",
        "COMPLIANCE_REVIEW",
        "REQUEST_CLIENT_CONSENT",
        "EXECUTE",
        "NONE",
    ] = Field(
        description="Recommended next workflow step based on gate policy.",
        examples=["REQUEST_CLIENT_CONSENT"],
    )
    reasons: List[GateReason] = Field(
        default_factory=list,
        description="Deterministic ordered reasons explaining the gate.",
    )
    summary: GateDecisionSummary = Field(description="Gate summary counters.")


class ProposedCashFlow(BaseModel):
    intent_type: Literal["CASH_FLOW"] = Field(
        default="CASH_FLOW",
        description="Intent discriminator for advisory cash-flow proposals.",
        examples=["CASH_FLOW"],
    )
    currency: str = Field(description="Cash-flow currency code.", examples=["USD"])
    amount: Decimal = Field(
        description="Signed cash-flow amount as decimal string.",
        examples=["2000.00", "-500.00"],
    )
    description: Optional[str] = Field(
        default=None,
        description="Optional advisor-entered narrative for this cash flow.",
        examples=["Client deposit before switch"],
    )

    @field_validator("amount", mode="before")
    @classmethod
    def reject_float_amount(cls, v: object) -> object:
        if _is_python_float(v):
            raise ValueError("PROPOSAL_INVALID_TRADE_INPUT: amount must be a decimal string")
        return v


class ProposedTrade(BaseModel):
    intent_type: Literal["SECURITY_TRADE"] = Field(
        default="SECURITY_TRADE",
        description="Intent discriminator for advisory security trades.",
        examples=["SECURITY_TRADE"],
    )
    side: Literal["BUY", "SELL"] = Field(description="Manual trade side.", examples=["BUY"])
    instrument_id: str = Field(
        description="Instrument identifier for manual trade.",
        examples=["EQ_GROWTH"],
    )
    quantity: Optional[Decimal] = Field(
        default=None,
        gt=0,
        description="Trade quantity. Required when `notional` is not provided.",
        examples=["40"],
    )
    notional: Optional[Money] = Field(
        default=None,
        description=(
            "Trade notional in instrument currency. Required when `quantity` is not provided."
        ),
        examples=[{"amount": "2000.00", "currency": "USD"}],
    )

    @field_validator("quantity", mode="before")
    @classmethod
    def reject_float_quantity(cls, v: object) -> object:
        if _is_python_float(v):
            raise ValueError("PROPOSAL_INVALID_TRADE_INPUT: quantity must be a decimal string")
        return v

    @field_validator("notional", mode="before")
    @classmethod
    def reject_float_notional_amount(cls, v: object) -> object:
        if isinstance(v, dict) and _is_python_float(v.get("amount")):
            raise ValueError(
                "PROPOSAL_INVALID_TRADE_INPUT: notional.amount must be a decimal string"
            )
        return v

    @model_validator(mode="after")
    def validate_quantity_or_notional(self) -> "ProposedTrade":
        if self.quantity is None and self.notional is None:
            raise ValueError("PROPOSAL_INVALID_TRADE_INPUT: quantity or notional is required")
        if self.quantity is not None and self.notional is not None:
            raise ValueError(
                "PROPOSAL_INVALID_TRADE_INPUT: provide either quantity or notional, not both"
            )
        if self.notional is not None and self.notional.amount <= Decimal("0"):
            raise ValueError("PROPOSAL_INVALID_TRADE_INPUT: notional.amount must be greater than 0")
        return self


class ProposalSimulateRequest(BaseModel):
    model_config = {
        "json_schema_extra": {
            "example": {
                "portfolio_snapshot": {
                    "portfolio_id": "pf_advisory_01",
                    "base_currency": "USD",
                    "positions": [{"instrument_id": "EQ_LEGACY", "quantity": "100"}],
                    "cash_balances": [{"currency": "USD", "amount": "5000.00"}],
                },
                "market_data_snapshot": {
                    "prices": [
                        {"instrument_id": "EQ_LEGACY", "price": "100.00", "currency": "USD"},
                        {"instrument_id": "EQ_GROWTH", "price": "50.00", "currency": "USD"},
                    ],
                    "fx_rates": [],
                },
                "shelf_entries": [
                    {"instrument_id": "EQ_LEGACY", "status": "APPROVED"},
                    {"instrument_id": "EQ_GROWTH", "status": "APPROVED"},
                ],
                "options": {
                    "enable_proposal_simulation": True,
                    "proposal_apply_cash_flows_first": True,
                    "proposal_block_negative_cash": True,
                    "block_on_missing_prices": True,
                    "block_on_missing_fx": True,
                },
                "proposed_cash_flows": [
                    {
                        "intent_type": "CASH_FLOW",
                        "currency": "USD",
                        "amount": "2000.00",
                        "description": "Client top-up",
                    }
                ],
                "proposed_trades": [
                    {
                        "intent_type": "SECURITY_TRADE",
                        "side": "BUY",
                        "instrument_id": "EQ_GROWTH",
                        "quantity": "40",
                    }
                ],
            }
        }
    }

    portfolio_snapshot: PortfolioSnapshot = Field(
        description="Current portfolio holdings and cash balances.",
        examples=[
            {
                "portfolio_id": "pf_advisory_01",
                "base_currency": "USD",
                "positions": [{"instrument_id": "EQ_LEGACY", "quantity": "100"}],
                "cash_balances": [{"currency": "USD", "amount": "5000.00"}],
            }
        ],
    )
    market_data_snapshot: MarketDataSnapshot = Field(
        description="Price and FX snapshot used for proposal simulation.",
        examples=[
            {
                "prices": [
                    {"instrument_id": "EQ_LEGACY", "price": "100.00", "currency": "USD"},
                    {"instrument_id": "EQ_GROWTH", "price": "50.00", "currency": "USD"},
                ],
                "fx_rates": [],
            }
        ],
    )
    shelf_entries: List[ShelfEntry] = Field(
        description="Instrument eligibility and policy metadata.",
        examples=[
            [
                {"instrument_id": "EQ_LEGACY", "status": "APPROVED"},
                {"instrument_id": "EQ_GROWTH", "status": "APPROVED"},
            ]
        ],
    )
    options: EngineOptions = Field(
        default_factory=EngineOptions,
        description="Request-level engine behavior and feature toggles.",
        examples=[
            {
                "enable_proposal_simulation": True,
                "proposal_apply_cash_flows_first": True,
                "proposal_block_negative_cash": True,
            }
        ],
    )
    proposed_cash_flows: List[ProposedCashFlow] = Field(
        default_factory=list,
        description="Advisor-entered cash flow instructions.",
        examples=[[{"intent_type": "CASH_FLOW", "currency": "USD", "amount": "2000.00"}]],
    )
    proposed_trades: List[ProposedTrade] = Field(
        default_factory=list,
        description="Advisor-entered manual security trade instructions.",
        examples=[
            [
                {
                    "intent_type": "SECURITY_TRADE",
                    "side": "BUY",
                    "instrument_id": "EQ_GROWTH",
                    "quantity": "40",
                }
            ]
        ],
    )
    reference_model: Optional[ReferenceModel] = Field(
        default=None,
        description="Optional reference model used for advisory drift analytics.",
    )


class ProposalResult(BaseModel):
    model_config = {
        "json_schema_extra": {
            "example": {
                "proposal_run_id": "pr_abc12345",
                "correlation_id": "corr_123abc",
                "status": "READY",
                "intents": [],
                "diagnostics": {
                    "warnings": [],
                    "data_quality": {"price_missing": [], "fx_missing": []},
                },
                "lineage": {"request_hash": "sha256:...", "idempotency_key": "idem-1"},
            }
        }
    }

    proposal_run_id: str = Field(description="Proposal run identifier.", examples=["pr_abc12345"])
    correlation_id: str = Field(
        description="Correlation id used by request logging context.",
        examples=["corr_123abc"],
    )
    status: Literal["READY", "BLOCKED", "PENDING_REVIEW"] = Field(
        description="Top-level domain outcome.",
        examples=["READY"],
    )
    before: SimulatedState = Field(description="Before-state valuation snapshot.")
    intents: List[Annotated[ProposalOrderIntent, Field(discriminator="intent_type")]] = Field(
        description="Deterministically ordered proposal intents applied during simulation.",
        examples=[
            [
                {
                    "intent_type": "CASH_FLOW",
                    "intent_id": "oi_cf_1",
                    "currency": "USD",
                    "amount": "2000.00",
                },
                {
                    "intent_type": "SECURITY_TRADE",
                    "intent_id": "oi_1",
                    "side": "BUY",
                    "instrument_id": "EQ_GROWTH",
                    "quantity": "40",
                },
            ]
        ],
    )
    after_simulated: SimulatedState = Field(description="After-state simulation snapshot.")
    reconciliation: Optional[Reconciliation] = Field(
        default=None, description="Reconciliation output."
    )
    rule_results: List[RuleResult] = Field(
        default_factory=list, description="Rule engine evaluations."
    )
    explanation: Dict[str, Any] = Field(description="Additional explanatory payload.")
    diagnostics: DiagnosticsData = Field(description="Diagnostics and warnings for the run.")
    drift_analysis: Optional[DriftAnalysis] = Field(
        default=None,
        description="Reference-model drift analytics when provided and enabled.",
    )
    suitability: Optional[SuitabilityResult] = Field(
        default=None,
        description="Advisory suitability scanner output with NEW/RESOLVED/PERSISTENT issues.",
    )
    gate_decision: Optional[GateDecision] = Field(
        default=None,
        description="Deterministic workflow gate decision for advisory workflow routing.",
    )
    lineage: LineageData = Field(description="Lineage identifiers and request hash.")
