from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, condecimal, model_validator


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


class ModelPortfolioDefinitionRecord(BaseModel):
    model_portfolio_id: str = Field(
        ...,
        description="Canonical model portfolio identifier.",
        examples=["MODEL_SG_BALANCED_DPM"],
    )
    model_portfolio_version: str = Field(
        ...,
        description="Approved model portfolio version.",
        examples=["2026.03"],
    )
    display_name: str = Field(
        ...,
        description="Business display name for the model portfolio.",
        examples=["Singapore Balanced DPM Model"],
    )
    base_currency: str = Field(..., description="Model base currency.", examples=["SGD"])
    risk_profile: str = Field(
        ...,
        description="Mandate risk profile aligned to this model.",
        examples=["balanced"],
    )
    mandate_type: str = Field(
        ...,
        description="Mandate type for which this model is approved.",
        examples=["discretionary"],
    )
    rebalance_frequency: str | None = Field(
        None,
        description="Expected rebalance cadence.",
        examples=["monthly"],
    )
    approval_status: Literal["approved", "draft", "retired", "suspended"] = Field(
        "approved",
        description="Model approval lifecycle status.",
        examples=["approved"],
    )
    approved_at: datetime | None = Field(
        None,
        description="Timestamp at which the model version was approved.",
        examples=["2026-03-20T09:00:00Z"],
    )
    effective_from: date = Field(
        ...,
        description="Model version effective start date.",
        examples=["2026-03-25"],
    )
    effective_to: date | None = Field(
        None,
        description="Model version effective end date, null when open-ended.",
        examples=["2026-12-31"],
    )
    source_system: str | None = Field(
        None,
        description="Upstream model portfolio source system.",
        examples=["investment_office_model_system"],
    )
    source_record_id: str | None = Field(
        None,
        description="Source record identifier for deterministic replay.",
        examples=["model_sg_balanced_202603"],
    )
    observed_at: datetime | None = Field(
        None,
        description="Timestamp when the upstream source observed or published the model definition.",
        examples=["2026-03-20T09:00:00Z"],
    )
    quality_status: str = Field(
        "accepted",
        description="Data quality status for the model definition.",
        examples=["accepted"],
    )

    model_config = ConfigDict()


class ModelPortfolioTargetRecord(BaseModel):
    model_portfolio_id: str = Field(
        ...,
        description="Canonical model portfolio identifier.",
        examples=["MODEL_SG_BALANCED_DPM"],
    )
    model_portfolio_version: str = Field(
        ...,
        description="Approved model portfolio version.",
        examples=["2026.03"],
    )
    instrument_id: str = Field(
        ...,
        description="Canonical instrument identifier.",
        examples=["EQ_US_AAPL"],
    )
    target_weight: condecimal(ge=Decimal(0), le=Decimal(1)) = Field(
        ...,
        description="Target instrument weight as a decimal ratio between 0 and 1.",
        examples=["0.1200000000"],
    )
    min_weight: condecimal(ge=Decimal(0), le=Decimal(1)) | None = Field(
        None,
        description="Optional minimum policy band for the instrument.",
        examples=["0.0800000000"],
    )
    max_weight: condecimal(ge=Decimal(0), le=Decimal(1)) | None = Field(
        None,
        description="Optional maximum policy band for the instrument.",
        examples=["0.1600000000"],
    )
    target_status: Literal["active", "inactive"] = Field(
        "active",
        description="Target lifecycle status.",
        examples=["active"],
    )
    effective_from: date = Field(
        ...,
        description="Target effective start date.",
        examples=["2026-03-25"],
    )
    effective_to: date | None = Field(
        None,
        description="Target effective end date, null when open-ended.",
        examples=["2026-12-31"],
    )
    source_system: str | None = Field(
        None,
        description="Upstream model target source system.",
        examples=["investment_office_model_system"],
    )
    source_record_id: str | None = Field(
        None,
        description="Source record identifier for deterministic replay.",
        examples=["model_sg_balanced_202603_eq_us_aapl"],
    )
    observed_at: datetime | None = Field(
        None,
        description="Timestamp when the upstream source observed or published the model target.",
        examples=["2026-03-20T09:00:00Z"],
    )
    quality_status: str = Field(
        "accepted",
        description="Data quality status for the model target.",
        examples=["accepted"],
    )

    @model_validator(mode="after")
    def validate_bands(self) -> "ModelPortfolioTargetRecord":
        if self.min_weight is not None and self.min_weight > self.target_weight:
            raise ValueError("min_weight must be less than or equal to target_weight")
        if self.max_weight is not None and self.max_weight < self.target_weight:
            raise ValueError("max_weight must be greater than or equal to target_weight")
        if (
            self.min_weight is not None
            and self.max_weight is not None
            and self.min_weight > self.max_weight
        ):
            raise ValueError("min_weight must be less than or equal to max_weight")
        return self

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
    benchmark_currency: str = Field(..., description="Benchmark currency.", examples=["USD"])
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
    index_currency: str = Field(..., description="Index currency.", examples=["USD"])
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
    series_currency: str = Field(..., description="Series currency code.", examples=["USD"])
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
    series_currency: str = Field(..., description="Series currency code.", examples=["USD"])
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
    series_currency: str = Field(..., description="Series currency code.", examples=["USD"])
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
    series_currency: str = Field(..., description="Series currency.", examples=["USD"])
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

    model_config = ConfigDict()


class ClassificationTaxonomyRecord(BaseModel):
    classification_set_id: str = Field(
        ..., description="Classification set identifier.", examples=["wm_global_taxonomy_v1"]
    )
    taxonomy_scope: str = Field(..., description="Taxonomy scope.", examples=["index"])
    dimension_name: str = Field(..., description="Dimension name.", examples=["sector"])
    dimension_value: str = Field(..., description="Dimension value.", examples=["technology"])
    dimension_description: str | None = Field(
        None,
        description="Dimension description.",
        examples=["Technology sector classification"],
    )
    effective_from: date = Field(..., description="Effective start date.", examples=["2025-01-01"])
    effective_to: date | None = Field(
        None, description="Effective end date.", examples=["2026-12-31"]
    )
    source_timestamp: datetime | None = Field(
        None,
        description="Source publication timestamp for the taxonomy record.",
        examples=["2026-01-31T23:00:00Z"],
    )
    source_vendor: str | None = Field(
        None, description="Source vendor.", examples=["LOTUS_TAXONOMY"]
    )
    source_record_id: str | None = Field(
        None, description="Source record identifier.", examples=["tax_20260131"]
    )
    quality_status: str = Field("accepted", description="Quality status.", examples=["accepted"])

    model_config = ConfigDict()


class CashAccountMasterRecord(BaseModel):
    cash_account_id: str = Field(
        ..., description="Canonical Lotus cash account identifier.", examples=["CASH-ACC-USD-001"]
    )
    portfolio_id: str = Field(
        ...,
        description="Owning portfolio identifier.",
        examples=["PORT-001"],
    )
    security_id: str = Field(
        ...,
        description="Linked cash instrument/security identifier.",
        examples=["CASH_USD"],
    )
    display_name: str = Field(
        ..., description="Cash account display name.", examples=["USD Operating Cash"]
    )
    account_currency: str = Field(
        ..., description="Native cash account currency.", examples=["USD"]
    )
    account_role: str | None = Field(
        None,
        description="Optional account role label.",
        examples=["OPERATING_CASH"],
    )
    lifecycle_status: str = Field(
        "ACTIVE",
        description="Cash account lifecycle status.",
        examples=["ACTIVE"],
    )
    opened_on: date | None = Field(
        None,
        description="Optional cash account open date.",
        examples=["2026-01-01"],
    )
    closed_on: date | None = Field(
        None,
        description="Optional cash account close date.",
        examples=["2026-12-31"],
    )
    source_system: str | None = Field(
        None,
        description="Upstream source system.",
        examples=["lotus-manage"],
    )
    source_record_id: str | None = Field(
        None,
        description="Upstream source record identifier.",
        examples=["cash-account-001"],
    )

    model_config = ConfigDict()


class InstrumentLookthroughComponentRecord(BaseModel):
    parent_security_id: str = Field(
        ...,
        description="Structured product or fund security identifier being decomposed.",
        examples=["FUND_GLOBAL_60_40"],
    )
    component_security_id: str = Field(
        ...,
        description="Underlying component security identifier.",
        examples=["ETF_WORLD_EQUITY"],
    )
    effective_from: date = Field(
        ...,
        description="Effective start date for the look-through composition row.",
        examples=["2026-01-01"],
    )
    effective_to: date | None = Field(
        None,
        description="Effective end date for the look-through composition row.",
        examples=["2026-12-31"],
    )
    component_weight: condecimal(ge=Decimal(0), le=Decimal(1)) = Field(
        ...,
        description="Weight of the underlying component between 0 and 1.",
        examples=["0.6000000000"],
    )
    source_system: str | None = Field(
        None,
        description="Upstream source system.",
        examples=["lotus-manage"],
    )
    source_record_id: str | None = Field(
        None,
        description="Upstream source record identifier.",
        examples=["lt-001"],
    )

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


class ClassificationTaxonomyIngestionRequest(BaseModel):
    classification_taxonomy: list[ClassificationTaxonomyRecord] = Field(
        ...,
        description="Classification taxonomy records to ingest or upsert.",
        min_length=1,
        examples=[
            [
                {
                    "classification_set_id": "wm_global_taxonomy_v1",
                    "taxonomy_scope": "index",
                    "dimension_name": "sector",
                    "dimension_value": "technology",
                    "effective_from": "2025-01-01",
                }
            ]
        ],
    )

    model_config = ConfigDict()


class CashAccountMasterIngestionRequest(BaseModel):
    cash_accounts: list[CashAccountMasterRecord] = Field(
        ...,
        description="Cash-account master records to ingest or upsert.",
        min_length=1,
        examples=[
            [
                {
                    "cash_account_id": "CASH-ACC-USD-001",
                    "portfolio_id": "PORT-001",
                    "security_id": "CASH_USD",
                    "display_name": "USD Operating Cash",
                    "account_currency": "USD",
                    "account_role": "OPERATING_CASH",
                    "lifecycle_status": "ACTIVE",
                }
            ]
        ],
    )

    model_config = ConfigDict()


class InstrumentLookthroughComponentIngestionRequest(BaseModel):
    lookthrough_components: list[InstrumentLookthroughComponentRecord] = Field(
        ...,
        description="Instrument look-through composition rows to ingest or upsert.",
        min_length=1,
        examples=[
            [
                {
                    "parent_security_id": "FUND_GLOBAL_60_40",
                    "component_security_id": "ETF_WORLD_EQUITY",
                    "effective_from": "2026-01-01",
                    "component_weight": "0.6000000000",
                }
            ]
        ],
    )

    model_config = ConfigDict()
