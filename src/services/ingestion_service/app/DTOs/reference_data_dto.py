from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from portfolio_common.currency_codes import normalize_currency_code
from pydantic import BaseModel, ConfigDict, Field, condecimal, field_validator, model_validator

from . import reference_data_client_preference_dto as _client_preference_dto
from . import reference_data_instrument_eligibility_dto as _instrument_eligibility_dto
from . import reference_data_model_portfolio_dto as _model_portfolio_dto
from . import reference_data_support_dto as _support_dto
from . import reference_data_tax_dto as _tax_dto

ClientRestrictionProfileIngestionRequest = (
    _client_preference_dto.ClientRestrictionProfileIngestionRequest
)
ClientRestrictionProfileRecord = _client_preference_dto.ClientRestrictionProfileRecord
SustainabilityPreferenceProfileIngestionRequest = (
    _client_preference_dto.SustainabilityPreferenceProfileIngestionRequest
)
SustainabilityPreferenceProfileRecord = _client_preference_dto.SustainabilityPreferenceProfileRecord
ClientTaxProfileIngestionRequest = _tax_dto.ClientTaxProfileIngestionRequest
ClientTaxProfileRecord = _tax_dto.ClientTaxProfileRecord
ClientTaxRuleSetIngestionRequest = _tax_dto.ClientTaxRuleSetIngestionRequest
ClientTaxRuleSetRecord = _tax_dto.ClientTaxRuleSetRecord
InstrumentEligibilityProfileIngestionRequest = (
    _instrument_eligibility_dto.InstrumentEligibilityProfileIngestionRequest
)
InstrumentEligibilityProfileRecord = _instrument_eligibility_dto.InstrumentEligibilityProfileRecord
ModelPortfolioDefinitionRecord = _model_portfolio_dto.ModelPortfolioDefinitionRecord
ModelPortfolioTargetRecord = _model_portfolio_dto.ModelPortfolioTargetRecord
CashAccountMasterIngestionRequest = _support_dto.CashAccountMasterIngestionRequest
CashAccountMasterRecord = _support_dto.CashAccountMasterRecord
ClassificationTaxonomyIngestionRequest = _support_dto.ClassificationTaxonomyIngestionRequest
ClassificationTaxonomyRecord = _support_dto.ClassificationTaxonomyRecord
InstrumentLookthroughComponentIngestionRequest = (
    _support_dto.InstrumentLookthroughComponentIngestionRequest
)
InstrumentLookthroughComponentRecord = _support_dto.InstrumentLookthroughComponentRecord


class PortfolioBenchmarkAssignmentRecord(BaseModel):
    portfolio_id: str = Field(
        ..., description="Canonical portfolio identifier.", examples=["DEMO_DPM_EUR_001"]
    )
    benchmark_id: str = Field(
        ...,
        description="Canonical benchmark identifier.",
        examples=["BMK_GLOBAL_BALANCED_60_40"],
    )
    effective_from: date = Field(
        ..., description="Assignment effective start date.", examples=["2025-01-01"]
    )
    effective_to: date | None = Field(
        None,
        description="Assignment effective end date, null for open-ended assignment.",
        examples=["2026-12-31"],
    )
    assignment_source: str = Field(
        ...,
        description="Source channel that established this benchmark assignment.",
        examples=["benchmark_policy_engine"],
    )
    assignment_status: str = Field(..., description="Assignment status.", examples=["active"])
    policy_pack_id: str | None = Field(
        None,
        description="Optional policy pack identifier.",
        examples=["policy_pack_wm_v1"],
    )
    source_system: str | None = Field(
        None, description="Upstream source system.", examples=["lotus-manage"]
    )
    assignment_recorded_at: datetime | None = Field(
        None,
        description=(
            "Optional assignment capture timestamp from the source system; "
            "defaults to ingestion time when omitted."
        ),
        examples=["2026-03-10T08:15:00Z"],
    )
    assignment_version: int = Field(
        1,
        description="Assignment version used for tie-breaks at same effective_from.",
        examples=[1],
        ge=1,
    )

    model_config = ConfigDict()


class DiscretionaryMandateBindingRecord(BaseModel):
    portfolio_id: str = Field(
        ..., description="Canonical portfolio identifier.", examples=["PB_SG_GLOBAL_BAL_001"]
    )
    mandate_id: str = Field(
        ...,
        description="Canonical discretionary mandate identifier.",
        examples=["MANDATE_PB_SG_GLOBAL_BAL_001"],
    )
    client_id: str = Field(
        ...,
        description="Canonical client identifier bound to the mandate.",
        examples=["CIF_SG_000184"],
    )
    mandate_type: Literal["discretionary"] = Field(
        "discretionary",
        description="Mandate type. Slice 5 supports discretionary mandate bindings only.",
        examples=["discretionary"],
    )
    discretionary_authority_status: Literal["active", "pending", "suspended", "terminated"] = Field(
        ...,
        description="Authority lifecycle status that determines DPM execution supportability.",
        examples=["active"],
    )
    booking_center_code: str = Field(
        ..., description="Booking center governing the mandate.", examples=["Singapore"]
    )
    jurisdiction_code: str = Field(
        ..., description="Legal or regulatory jurisdiction code for the mandate.", examples=["SG"]
    )
    model_portfolio_id: str = Field(
        ...,
        description="Approved model portfolio identifier selected for the mandate.",
        examples=["MODEL_PB_SG_GLOBAL_BAL_DPM"],
    )
    policy_pack_id: str | None = Field(
        None,
        description="Policy pack identifier applied to DPM checks for this mandate.",
        examples=["POLICY_DPM_SG_BALANCED_V1"],
    )
    mandate_objective: str | None = Field(
        None,
        description=(
            "Source-owned discretionary mandate objective used by mandate twins and health "
            "checks. This is mandate administration truth, not a local portfolio default."
        ),
        examples=["Preserve and grow global balanced wealth within controlled drawdown limits."],
    )
    risk_profile: str = Field(..., description="Mandate risk profile.", examples=["balanced"])
    investment_horizon: str = Field(
        ..., description="Mandate investment horizon classification.", examples=["long_term"]
    )
    review_cadence: str | None = Field(
        None,
        description="Mandate review cadence from the mandate administration source.",
        examples=["quarterly"],
    )
    last_review_date: date | None = Field(
        None,
        description="Most recent completed discretionary mandate review date.",
        examples=["2026-03-31"],
    )
    next_review_due_date: date | None = Field(
        None,
        description="Next due discretionary mandate review date.",
        examples=["2026-06-30"],
    )
    leverage_allowed: bool = Field(
        False, description="Whether leverage is permitted by the mandate.", examples=[False]
    )
    tax_awareness_allowed: bool = Field(
        False, description="Whether tax-aware DPM execution is allowed.", examples=[True]
    )
    settlement_awareness_required: bool = Field(
        False,
        description="Whether DPM execution must account for settlement constraints.",
        examples=[True],
    )
    rebalance_frequency: str = Field(
        ..., description="Expected rebalance cadence.", examples=["monthly"]
    )
    rebalance_bands: dict[str, str] = Field(
        ...,
        description=(
            "Mandate-level rebalance band settings. Values are decimal strings to preserve "
            "source precision."
        ),
        examples=[{"default_band": "0.0250000000", "cash_reserve_weight": "0.0200000000"}],
    )
    effective_from: date = Field(
        ..., description="Binding effective start date.", examples=["2026-04-01"]
    )
    effective_to: date | None = Field(
        None,
        description="Binding effective end date, null when open-ended.",
        examples=["2026-12-31"],
    )
    binding_version: int = Field(
        1, description="Binding version used for deterministic effective-date tie-breaks.", ge=1
    )
    source_system: str | None = Field(
        None,
        description="Upstream mandate administration source system.",
        examples=["mandate_admin"],
    )
    source_record_id: str | None = Field(
        None,
        description="Source record identifier for deterministic replay.",
        examples=["mandate_001_v1"],
    )
    observed_at: datetime | None = Field(
        None,
        description="Timestamp when the upstream source observed or published the binding.",
        examples=["2026-04-01T09:00:00Z"],
    )
    quality_status: str = Field(
        "accepted",
        description="Data quality status for the mandate binding.",
        examples=["accepted"],
    )

    @model_validator(mode="after")
    def validate_effective_window(self) -> "DiscretionaryMandateBindingRecord":
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be on or after effective_from")
        return self

    model_config = ConfigDict()


class ClientIncomeNeedsScheduleRecord(BaseModel):
    client_id: str = Field(..., description="Client identifier bound to the income-needs schedule.")
    portfolio_id: str = Field(..., description="Portfolio identifier for the schedule.")
    mandate_id: str | None = Field(None, description="Mandate identifier when schedule-specific.")
    schedule_id: str = Field(..., description="Source-owned income-needs schedule identifier.")
    need_type: Literal[
        "RECURRING_WITHDRAWAL", "LIVING_EXPENSE", "COMMITTED_OUTFLOW", "INCOME_NEED", "OTHER"
    ] = Field(..., description="Bounded income need type.")
    need_status: Literal["active", "inactive", "suspended"] = Field(
        "active", description="Income-needs lifecycle status."
    )
    amount: condecimal(gt=Decimal(0)) = Field(
        ..., description="Source-supplied amount for the income need."
    )
    currency: str = Field(
        ...,
        description=(
            "Canonical three-letter currency for the income-needs amount used by cashflow, "
            "liquidity, and funding calculations."
        ),
    )
    frequency: Literal["ONE_TIME", "MONTHLY", "QUARTERLY", "SEMI_ANNUAL", "ANNUAL"] = Field(
        ..., description="Source-supplied income-needs frequency."
    )
    start_date: date = Field(..., description="Income-needs schedule start date.")
    end_date: date | None = Field(None, description="Income-needs schedule end date.")
    priority: int = Field(1, ge=1)
    funding_policy: str | None = Field(None)
    source_system: str | None = Field(None)
    source_record_id: str | None = Field(None)
    observed_at: datetime | None = Field(None)
    quality_status: str = Field("accepted")

    @field_validator("currency", mode="before")
    @classmethod
    def _normalize_currency(cls, value: object) -> str:
        return normalize_currency_code(value)

    @model_validator(mode="after")
    def validate_schedule(self) -> "ClientIncomeNeedsScheduleRecord":
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self

    model_config = ConfigDict()


class LiquidityReserveRequirementRecord(BaseModel):
    client_id: str = Field(..., description="Client identifier bound to the reserve requirement.")
    portfolio_id: str = Field(..., description="Portfolio identifier for the reserve requirement.")
    mandate_id: str | None = Field(
        None, description="Mandate identifier when requirement-specific."
    )
    reserve_requirement_id: str = Field(..., description="Source-owned reserve requirement id.")
    reserve_type: Literal[
        "MIN_CASH_BUFFER", "SPENDING_RESERVE", "LIQUIDITY_BUCKET", "POLICY_MINIMUM", "OTHER"
    ] = Field(..., description="Bounded reserve requirement type.")
    reserve_status: Literal["active", "inactive", "suspended"] = Field(
        "active", description="Reserve requirement lifecycle status."
    )
    required_amount: condecimal(gt=Decimal(0)) = Field(
        ..., description="Required reserve amount supplied by the source."
    )
    currency: str = Field(
        ...,
        description=(
            "Canonical three-letter currency for the reserve amount used by liquidity and "
            "policy-compliance calculations."
        ),
    )
    horizon_days: int = Field(..., ge=0)
    priority: int = Field(1, ge=1)
    policy_source: str = Field(..., description="Source policy or bank reference for requirement.")
    effective_from: date = Field(..., description="Requirement effective start date.")
    effective_to: date | None = Field(None, description="Requirement effective end date.")
    requirement_version: int = Field(1, ge=1)
    source_system: str | None = Field(None)
    source_record_id: str | None = Field(None)
    observed_at: datetime | None = Field(None)
    quality_status: str = Field("accepted")

    @field_validator("currency", mode="before")
    @classmethod
    def _normalize_currency(cls, value: object) -> str:
        return normalize_currency_code(value)

    @model_validator(mode="after")
    def validate_requirement(self) -> "LiquidityReserveRequirementRecord":
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be on or after effective_from")
        return self

    model_config = ConfigDict()


class PlannedWithdrawalScheduleRecord(BaseModel):
    client_id: str = Field(..., description="Client identifier bound to the withdrawal schedule.")
    portfolio_id: str = Field(..., description="Portfolio identifier for the withdrawal schedule.")
    mandate_id: str | None = Field(None, description="Mandate identifier when withdrawal-specific.")
    withdrawal_schedule_id: str = Field(..., description="Source-owned withdrawal schedule id.")
    withdrawal_type: Literal["PLANNED_WITHDRAWAL", "INCOME_DISTRIBUTION", "OTHER"] = Field(
        ..., description="Bounded planned withdrawal type."
    )
    withdrawal_status: Literal["active", "inactive", "suspended", "cancelled"] = Field(
        "active", description="Withdrawal lifecycle status."
    )
    amount: condecimal(gt=Decimal(0)) = Field(
        ..., description="Source-supplied planned withdrawal amount."
    )
    currency: str = Field(
        ...,
        description=(
            "Canonical three-letter currency for the planned withdrawal amount used by "
            "cashflow and liquidity planning calculations."
        ),
    )
    scheduled_date: date = Field(..., description="Scheduled withdrawal date.")
    recurrence_frequency: (
        Literal["ONE_TIME", "MONTHLY", "QUARTERLY", "SEMI_ANNUAL", "ANNUAL"] | None
    ) = Field(None)
    purpose_code: str | None = Field(None)
    source_system: str | None = Field(None)
    source_record_id: str | None = Field(None)
    observed_at: datetime | None = Field(None)
    quality_status: str = Field("accepted")

    @field_validator("currency", mode="before")
    @classmethod
    def _normalize_currency(cls, value: object) -> str:
        return normalize_currency_code(value)

    model_config = ConfigDict()


class BenchmarkDefinitionRecord(BaseModel):
    benchmark_id: str = Field(
        ..., description="Canonical benchmark identifier.", examples=["BMK_GLOBAL_BALANCED_60_40"]
    )
    benchmark_name: str = Field(
        ..., description="Benchmark display name.", examples=["Global Balanced 60/40 (TR)"]
    )
    benchmark_type: Literal["single_index", "composite"] = Field(
        ...,
        description="Benchmark type.",
        examples=["composite"],
    )
    benchmark_currency: str = Field(
        ...,
        description=(
            "Canonical three-letter benchmark currency used for performance comparison, "
            "policy evidence, and reporting alignment."
        ),
        examples=["USD"],
    )
    return_convention: Literal["price_return_index", "total_return_index"] = Field(
        ...,
        description="Benchmark return convention.",
        examples=["total_return_index"],
    )
    benchmark_status: str = Field("active", description="Benchmark status.", examples=["active"])
    benchmark_family: str | None = Field(
        None,
        description="Benchmark family grouping.",
        examples=["multi_asset_strategic"],
    )
    benchmark_provider: str | None = Field(
        None,
        description="Benchmark provider name.",
        examples=["MSCI"],
    )
    rebalance_frequency: str | None = Field(
        None,
        description="Rebalance frequency for composite benchmarks.",
        examples=["quarterly"],
    )
    classification_set_id: str | None = Field(
        None,
        description="Classification taxonomy set identifier.",
        examples=["wm_global_taxonomy_v1"],
    )
    classification_labels: dict[str, str] = Field(
        default_factory=dict,
        description="Canonical classification labels.",
        examples=[{"asset_class": "multi_asset", "region": "global"}],
    )
    effective_from: date = Field(
        ..., description="Definition effective start date.", examples=["2025-01-01"]
    )
    effective_to: date | None = Field(
        None, description="Definition effective end date.", examples=["2026-12-31"]
    )
    source_timestamp: datetime | None = Field(
        None,
        description="Source publication timestamp for the benchmark definition payload.",
        examples=["2026-01-31T23:00:00Z"],
    )
    source_vendor: str | None = Field(None, description="Source vendor.", examples=["MSCI"])
    source_record_id: str | None = Field(
        None, description="Source record identifier.", examples=["bmk_v20260131"]
    )
    quality_status: str = Field("accepted", description="Quality status.", examples=["accepted"])

    @field_validator("benchmark_currency", mode="before")
    @classmethod
    def _normalize_benchmark_currency(cls, value: object) -> str:
        return normalize_currency_code(value)

    model_config = ConfigDict()


class BenchmarkCompositionRecord(BaseModel):
    benchmark_id: str = Field(
        ..., description="Benchmark identifier.", examples=["BMK_GLOBAL_BALANCED_60_40"]
    )
    index_id: str = Field(
        ..., description="Component index identifier.", examples=["IDX_MSCI_WORLD_TR"]
    )
    composition_effective_from: date = Field(
        ...,
        description="Composition effective start date.",
        examples=["2026-01-01"],
    )
    composition_effective_to: date | None = Field(
        None,
        description="Composition effective end date.",
        examples=["2026-03-31"],
    )
    composition_weight: condecimal(ge=Decimal(0), le=Decimal(1)) = Field(
        ...,
        description="Component weight between 0 and 1.",
        examples=["0.6000000000"],
    )
    rebalance_event_id: str | None = Field(
        None,
        description="Rebalance event identifier.",
        examples=["rebalance_2026q1"],
    )
    source_timestamp: datetime | None = Field(
        None,
        description="Source publication timestamp for the benchmark composition payload.",
        examples=["2026-01-31T23:00:00Z"],
    )
    source_vendor: str | None = Field(None, description="Source vendor.", examples=["MSCI"])
    source_record_id: str | None = Field(
        None, description="Source record identifier.", examples=["cmp_v20260131"]
    )
    quality_status: str = Field("accepted", description="Quality status.", examples=["accepted"])

    model_config = ConfigDict()


class IndexDefinitionRecord(BaseModel):
    index_id: str = Field(
        ..., description="Canonical index identifier.", examples=["IDX_MSCI_WORLD_TR"]
    )
    index_name: str = Field(
        ..., description="Index display name.", examples=["MSCI World Total Return"]
    )
    index_currency: str = Field(
        ...,
        description=(
            "Canonical three-letter index currency used for benchmark construction, "
            "performance comparison, and reporting alignment."
        ),
        examples=["USD"],
    )
    index_type: str | None = Field(
        None, description="Index type descriptor.", examples=["equity_index"]
    )
    index_status: str = Field("active", description="Index status.", examples=["active"])
    index_provider: str | None = Field(None, description="Index provider.", examples=["MSCI"])
    index_market: str | None = Field(
        None,
        description="Index market or universe scope.",
        examples=["global_developed"],
    )
    classification_set_id: str | None = Field(
        None,
        description="Classification taxonomy set identifier.",
        examples=["wm_global_taxonomy_v1"],
    )
    classification_labels: dict[str, str] = Field(
        default_factory=dict,
        description="Canonical classification labels for attribution.",
        examples=[{"asset_class": "equity", "sector": "technology", "region": "global"}],
    )
    effective_from: date = Field(
        ..., description="Definition effective start date.", examples=["2025-01-01"]
    )
    effective_to: date | None = Field(
        None, description="Definition effective end date.", examples=["2026-12-31"]
    )
    source_timestamp: datetime | None = Field(
        None,
        description="Source publication timestamp for the index definition payload.",
        examples=["2026-01-31T23:00:00Z"],
    )
    source_vendor: str | None = Field(None, description="Source vendor.", examples=["MSCI"])
    source_record_id: str | None = Field(
        None, description="Source record identifier.", examples=["idx_v20260131"]
    )
    quality_status: str = Field("accepted", description="Quality status.", examples=["accepted"])

    @field_validator("index_currency", mode="before")
    @classmethod
    def _normalize_index_currency(cls, value: object) -> str:
        return normalize_currency_code(value)

    model_config = ConfigDict()


class IndexPriceSeriesRecord(BaseModel):
    series_id: str = Field(
        ..., description="Series identifier.", examples=["series_idx_world_price"]
    )
    index_id: str = Field(..., description="Index identifier.", examples=["IDX_MSCI_WORLD_TR"])
    series_date: date = Field(..., description="Series date.", examples=["2026-01-02"])
    index_price: condecimal(gt=Decimal(0)) = Field(
        ..., description="Index price value.", examples=["4567.1234000000"]
    )
    series_currency: str = Field(
        ...,
        description="Canonical three-letter currency for the index price series.",
        examples=["USD"],
    )
    value_convention: str = Field(
        ..., description="Value convention label.", examples=["close_price"]
    )
    source_timestamp: datetime | None = Field(
        None,
        description="Source publication timestamp for the index price series record.",
        examples=["2026-01-02T21:00:00Z"],
    )
    source_vendor: str | None = Field(None, description="Source vendor.", examples=["MSCI"])
    source_record_id: str | None = Field(
        None, description="Source record identifier.", examples=["idxp_20260102"]
    )
    quality_status: str = Field("accepted", description="Quality status.", examples=["accepted"])

    @field_validator("series_currency", mode="before")
    @classmethod
    def _normalize_series_currency(cls, value: object) -> str:
        return normalize_currency_code(value)

    model_config = ConfigDict()


class IndexReturnSeriesRecord(BaseModel):
    series_id: str = Field(..., description="Series identifier.", examples=["series_idx_world_ret"])
    index_id: str = Field(..., description="Index identifier.", examples=["IDX_MSCI_WORLD_TR"])
    series_date: date = Field(..., description="Series date.", examples=["2026-01-02"])
    index_return: Decimal = Field(..., description="Index return value.", examples=["0.0023000000"])
    return_period: str = Field(..., description="Return period label.", examples=["1d"])
    return_convention: str = Field(
        ..., description="Return convention label.", examples=["total_return_index"]
    )
    series_currency: str = Field(
        ...,
        description="Canonical three-letter currency for the index return series.",
        examples=["USD"],
    )
    source_timestamp: datetime | None = Field(
        None,
        description="Source publication timestamp for the index return series record.",
        examples=["2026-01-02T21:00:00Z"],
    )
    source_vendor: str | None = Field(None, description="Source vendor.", examples=["MSCI"])
    source_record_id: str | None = Field(
        None, description="Source record identifier.", examples=["idxr_20260102"]
    )
    quality_status: str = Field("accepted", description="Quality status.", examples=["accepted"])

    @field_validator("series_currency", mode="before")
    @classmethod
    def _normalize_series_currency(cls, value: object) -> str:
        return normalize_currency_code(value)

    model_config = ConfigDict()


class BenchmarkReturnSeriesRecord(BaseModel):
    series_id: str = Field(..., description="Series identifier.", examples=["series_bmk_60_40_ret"])
    benchmark_id: str = Field(
        ..., description="Benchmark identifier.", examples=["BMK_GLOBAL_BALANCED_60_40"]
    )
    series_date: date = Field(..., description="Series date.", examples=["2026-01-02"])
    benchmark_return: Decimal = Field(
        ..., description="Benchmark return value.", examples=["0.0019000000"]
    )
    return_period: str = Field(..., description="Return period label.", examples=["1d"])
    return_convention: str = Field(
        ..., description="Return convention label.", examples=["total_return_index"]
    )
    series_currency: str = Field(
        ...,
        description="Canonical three-letter currency for the benchmark return series.",
        examples=["USD"],
    )
    source_timestamp: datetime | None = Field(
        None,
        description="Source publication timestamp for the benchmark return series record.",
        examples=["2026-01-02T21:00:00Z"],
    )
    source_vendor: str | None = Field(None, description="Source vendor.", examples=["MSCI"])
    source_record_id: str | None = Field(
        None, description="Source record identifier.", examples=["bmkr_20260102"]
    )
    quality_status: str = Field("accepted", description="Quality status.", examples=["accepted"])

    @field_validator("series_currency", mode="before")
    @classmethod
    def _normalize_series_currency(cls, value: object) -> str:
        return normalize_currency_code(value)

    model_config = ConfigDict()


class RiskFreeSeriesRecord(BaseModel):
    series_id: str = Field(..., description="Series identifier.", examples=["rf_usd_3m"])
    risk_free_curve_id: str = Field(
        ..., description="Risk-free curve identifier.", examples=["USD_SOFR_3M"]
    )
    series_date: date = Field(..., description="Series date.", examples=["2026-01-02"])
    value: Decimal = Field(..., description="Risk-free value.", examples=["0.0350000000"])
    value_convention: Literal["annualized_rate", "period_return"] = Field(
        ...,
        description="Risk-free value convention.",
        examples=["annualized_rate"],
    )
    day_count_convention: str | None = Field(
        None,
        description="Day-count convention for annualized rates.",
        examples=["act_360"],
    )
    compounding_convention: str | None = Field(
        None,
        description="Compounding convention.",
        examples=["simple"],
    )
    series_currency: str = Field(
        ...,
        description="Canonical three-letter currency for the risk-free series.",
        examples=["USD"],
    )
    source_timestamp: datetime | None = Field(
        None,
        description="Source publication timestamp for the risk-free curve series record.",
        examples=["2026-01-02T06:00:00Z"],
    )
    source_vendor: str | None = Field(None, description="Source vendor.", examples=["BLOOMBERG"])
    source_record_id: str | None = Field(
        None, description="Source record identifier.", examples=["rf_20260102"]
    )
    quality_status: str = Field("accepted", description="Quality status.", examples=["accepted"])

    @field_validator("series_currency", mode="before")
    @classmethod
    def _normalize_series_currency(cls, value: object) -> str:
        return normalize_currency_code(value)

    model_config = ConfigDict()


class PortfolioBenchmarkAssignmentIngestionRequest(BaseModel):
    benchmark_assignments: list[PortfolioBenchmarkAssignmentRecord] = Field(
        ...,
        description="Portfolio benchmark assignment records to ingest or upsert.",
        min_length=1,
        examples=[
            [
                {
                    "portfolio_id": "DEMO_DPM_EUR_001",
                    "benchmark_id": "BMK_GLOBAL_BALANCED_60_40",
                    "effective_from": "2025-01-01",
                    "assignment_source": "benchmark_policy_engine",
                    "assignment_status": "active",
                }
            ]
        ],
    )

    model_config = ConfigDict()


class DiscretionaryMandateBindingIngestionRequest(BaseModel):
    mandate_bindings: list[DiscretionaryMandateBindingRecord] = Field(
        ...,
        description="Effective-dated discretionary mandate binding records to ingest or upsert.",
        min_length=1,
        examples=[
            [
                {
                    "portfolio_id": "PB_SG_GLOBAL_BAL_001",
                    "mandate_id": "MANDATE_PB_SG_GLOBAL_BAL_001",
                    "client_id": "CIF_SG_000184",
                    "mandate_type": "discretionary",
                    "discretionary_authority_status": "active",
                    "booking_center_code": "Singapore",
                    "jurisdiction_code": "SG",
                    "model_portfolio_id": "MODEL_PB_SG_GLOBAL_BAL_DPM",
                    "policy_pack_id": "POLICY_DPM_SG_BALANCED_V1",
                    "risk_profile": "balanced",
                    "investment_horizon": "long_term",
                    "tax_awareness_allowed": True,
                    "settlement_awareness_required": True,
                    "rebalance_frequency": "monthly",
                    "rebalance_bands": {
                        "default_band": "0.0250000000",
                        "cash_reserve_weight": "0.0200000000",
                    },
                    "effective_from": "2026-04-01",
                }
            ]
        ],
    )

    @model_validator(mode="after")
    def validate_binding_uniqueness(self) -> "DiscretionaryMandateBindingIngestionRequest":
        keys = [
            (
                binding.portfolio_id,
                binding.mandate_id,
                binding.effective_from,
                binding.binding_version,
            )
            for binding in self.mandate_bindings
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("mandate_bindings contains duplicate binding records")
        return self

    model_config = ConfigDict()


class ClientIncomeNeedsScheduleIngestionRequest(BaseModel):
    income_needs_schedules: list[ClientIncomeNeedsScheduleRecord] = Field(
        ...,
        description="Effective-dated client income-needs schedules to ingest or upsert.",
        min_length=1,
    )

    @model_validator(mode="after")
    def validate_schedule_uniqueness(self) -> "ClientIncomeNeedsScheduleIngestionRequest":
        keys = [
            (
                schedule.client_id,
                schedule.portfolio_id,
                schedule.schedule_id,
                schedule.start_date,
            )
            for schedule in self.income_needs_schedules
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("income_needs_schedules contains duplicate effective records")
        return self

    model_config = ConfigDict()


class LiquidityReserveRequirementIngestionRequest(BaseModel):
    liquidity_reserve_requirements: list[LiquidityReserveRequirementRecord] = Field(
        ...,
        description="Effective-dated liquidity reserve requirements to ingest or upsert.",
        min_length=1,
    )

    @model_validator(mode="after")
    def validate_requirement_uniqueness(self) -> "LiquidityReserveRequirementIngestionRequest":
        keys = [
            (
                requirement.client_id,
                requirement.portfolio_id,
                requirement.reserve_requirement_id,
                requirement.effective_from,
                requirement.requirement_version,
            )
            for requirement in self.liquidity_reserve_requirements
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("liquidity_reserve_requirements contains duplicate effective records")
        return self

    model_config = ConfigDict()


class PlannedWithdrawalScheduleIngestionRequest(BaseModel):
    planned_withdrawal_schedules: list[PlannedWithdrawalScheduleRecord] = Field(
        ...,
        description="Planned withdrawal schedules to ingest or upsert.",
        min_length=1,
    )

    @model_validator(mode="after")
    def validate_withdrawal_uniqueness(self) -> "PlannedWithdrawalScheduleIngestionRequest":
        keys = [
            (
                withdrawal.client_id,
                withdrawal.portfolio_id,
                withdrawal.withdrawal_schedule_id,
                withdrawal.scheduled_date,
            )
            for withdrawal in self.planned_withdrawal_schedules
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("planned_withdrawal_schedules contains duplicate effective records")
        return self

    model_config = ConfigDict()


class ModelPortfolioDefinitionIngestionRequest(BaseModel):
    model_portfolios: list[ModelPortfolioDefinitionRecord] = Field(
        ...,
        description="Model portfolio definition records to ingest or upsert.",
        min_length=1,
        examples=[
            [
                {
                    "model_portfolio_id": "MODEL_SG_BALANCED_DPM",
                    "model_portfolio_version": "2026.03",
                    "display_name": "Singapore Balanced DPM Model",
                    "base_currency": "SGD",
                    "risk_profile": "balanced",
                    "mandate_type": "discretionary",
                    "rebalance_frequency": "monthly",
                    "approval_status": "approved",
                    "effective_from": "2026-03-25",
                }
            ]
        ],
    )

    model_config = ConfigDict()


class ModelPortfolioTargetIngestionRequest(BaseModel):
    model_portfolio_targets: list[ModelPortfolioTargetRecord] = Field(
        ...,
        description="Model portfolio target records to ingest or upsert.",
        min_length=1,
        examples=[
            [
                {
                    "model_portfolio_id": "MODEL_SG_BALANCED_DPM",
                    "model_portfolio_version": "2026.03",
                    "instrument_id": "EQ_US_AAPL",
                    "target_weight": "0.1200000000",
                    "min_weight": "0.0800000000",
                    "max_weight": "0.1600000000",
                    "target_status": "active",
                    "effective_from": "2026-03-25",
                }
            ]
        ],
    )

    @model_validator(mode="after")
    def validate_target_uniqueness(self) -> "ModelPortfolioTargetIngestionRequest":
        keys = [
            (
                target.model_portfolio_id,
                target.model_portfolio_version,
                target.instrument_id,
                target.effective_from,
            )
            for target in self.model_portfolio_targets
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("model_portfolio_targets contains duplicate target records")
        return self

    model_config = ConfigDict()


class BenchmarkDefinitionIngestionRequest(BaseModel):
    benchmark_definitions: list[BenchmarkDefinitionRecord] = Field(
        ...,
        description="Benchmark definition records to ingest or upsert.",
        min_length=1,
        examples=[
            [
                {
                    "benchmark_id": "BMK_GLOBAL_BALANCED_60_40",
                    "benchmark_name": "Global Balanced 60/40 (TR)",
                    "benchmark_type": "composite",
                    "benchmark_currency": "USD",
                    "return_convention": "total_return_index",
                    "effective_from": "2025-01-01",
                }
            ]
        ],
    )

    model_config = ConfigDict()


class BenchmarkCompositionIngestionRequest(BaseModel):
    benchmark_compositions: list[BenchmarkCompositionRecord] = Field(
        ...,
        description="Benchmark composition records to ingest or upsert.",
        min_length=1,
        examples=[
            [
                {
                    "benchmark_id": "BMK_GLOBAL_BALANCED_60_40",
                    "index_id": "IDX_MSCI_WORLD_TR",
                    "composition_effective_from": "2026-01-01",
                    "composition_weight": "0.6000000000",
                }
            ]
        ],
    )

    model_config = ConfigDict()


class IndexDefinitionIngestionRequest(BaseModel):
    indices: list[IndexDefinitionRecord] = Field(
        ...,
        description="Index definition records to ingest or upsert.",
        min_length=1,
        examples=[
            [
                {
                    "index_id": "IDX_MSCI_WORLD_TR",
                    "index_name": "MSCI World Total Return",
                    "index_currency": "USD",
                    "effective_from": "2025-01-01",
                }
            ]
        ],
    )

    model_config = ConfigDict()


class IndexPriceSeriesIngestionRequest(BaseModel):
    index_price_series: list[IndexPriceSeriesRecord] = Field(
        ...,
        description="Index price series records to ingest or upsert.",
        min_length=1,
        examples=[
            [
                {
                    "series_id": "series_idx_world_price",
                    "index_id": "IDX_MSCI_WORLD_TR",
                    "series_date": "2026-01-02",
                    "index_price": "4567.1234000000",
                    "series_currency": "USD",
                    "value_convention": "close_price",
                }
            ]
        ],
    )

    model_config = ConfigDict()


class IndexReturnSeriesIngestionRequest(BaseModel):
    index_return_series: list[IndexReturnSeriesRecord] = Field(
        ...,
        description="Index return series records to ingest or upsert.",
        min_length=1,
        examples=[
            [
                {
                    "series_id": "series_idx_world_ret",
                    "index_id": "IDX_MSCI_WORLD_TR",
                    "series_date": "2026-01-02",
                    "index_return": "0.0023000000",
                    "return_period": "1d",
                    "return_convention": "total_return_index",
                    "series_currency": "USD",
                }
            ]
        ],
    )

    model_config = ConfigDict()


class BenchmarkReturnSeriesIngestionRequest(BaseModel):
    benchmark_return_series: list[BenchmarkReturnSeriesRecord] = Field(
        ...,
        description="Benchmark return series records to ingest or upsert.",
        min_length=1,
        examples=[
            [
                {
                    "series_id": "series_bmk_60_40_ret",
                    "benchmark_id": "BMK_GLOBAL_BALANCED_60_40",
                    "series_date": "2026-01-02",
                    "benchmark_return": "0.0019000000",
                    "return_period": "1d",
                    "return_convention": "total_return_index",
                    "series_currency": "USD",
                }
            ]
        ],
    )

    model_config = ConfigDict()


class RiskFreeSeriesIngestionRequest(BaseModel):
    risk_free_series: list[RiskFreeSeriesRecord] = Field(
        ...,
        description="Risk-free series records to ingest or upsert.",
        min_length=1,
        examples=[
            [
                {
                    "series_id": "rf_usd_3m",
                    "risk_free_curve_id": "USD_SOFR_3M",
                    "series_date": "2026-01-02",
                    "value": "0.0350000000",
                    "value_convention": "annualized_rate",
                    "series_currency": "USD",
                }
            ]
        ],
    )

    model_config = ConfigDict()
