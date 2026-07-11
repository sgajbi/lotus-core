from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from portfolio_common.source_data_product_metadata import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)
from pydantic import BaseModel, ConfigDict, Field

from .reference_integration_common_dto import IntegrationWindow


class BenchmarkDefinitionRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="Point-in-time date used to resolve benchmark definition version.",
        examples=["2026-01-31"],
    )

    model_config = ConfigDict()


class SeriesRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        description="As-of date used for effective definition/composition resolution.",
        examples=["2026-01-31"],
    )
    window: IntegrationWindow = Field(
        ...,
        description="Date window for series extraction.",
    )
    frequency: Literal["daily"] = Field(
        ...,
        description="Requested output frequency label. Currently only daily is supported.",
        examples=["daily"],
    )

    model_config = ConfigDict()


from .reference_integration_benchmark_market_series_dto import (  # noqa: E402, F401
    BenchmarkMarketSeriesRequest,
    BenchmarkMarketSeriesResponse,
    ComponentSeriesResponse,
    SeriesPoint,
)


class IndexSeriesRequest(SeriesRequest):
    target_currency: str | None = Field(
        None,
        description="Optional target currency context for price series responses.",
        examples=["USD"],
    )

    model_config = ConfigDict()


class BenchmarkReturnSeriesRequest(SeriesRequest):
    model_config = ConfigDict()


class RiskFreeSeriesRequest(SeriesRequest):
    currency: str = Field(
        ...,
        description="Series currency.",
        examples=["USD"],
    )
    series_mode: Literal["annualized_rate_series", "return_series"] = Field(
        ...,
        description="Risk-free series mode requested by the integration client.",
        examples=["annualized_rate_series"],
    )

    model_config = ConfigDict()


class IndexPriceSeriesPoint(BaseModel):
    series_date: date = Field(..., description="Series date.", examples=["2026-01-02"])
    index_price: Decimal = Field(
        ..., description="Index price value.", examples=["4567.1234000000"]
    )
    series_currency: str = Field(..., description="Series currency code.", examples=["USD"])
    value_convention: str = Field(
        ...,
        description="Value convention label for price series.",
        examples=["close_price"],
    )
    quality_status: str = Field(..., description="Quality status.", examples=["accepted"])

    model_config = ConfigDict()


class IndexReturnSeriesPoint(BaseModel):
    series_date: date = Field(..., description="Series date.", examples=["2026-01-02"])
    index_return: Decimal = Field(..., description="Index return value.", examples=["0.0023000000"])
    return_period: str = Field(..., description="Return period label.", examples=["1d"])
    return_convention: str = Field(
        ..., description="Return convention label.", examples=["total_return_index"]
    )
    series_currency: str = Field(..., description="Series currency code.", examples=["USD"])
    quality_status: str = Field(..., description="Quality status.", examples=["accepted"])

    model_config = ConfigDict()


class BenchmarkReturnSeriesPoint(BaseModel):
    series_date: date = Field(..., description="Series date.", examples=["2026-01-02"])
    benchmark_return: Decimal = Field(
        ..., description="Benchmark return value.", examples=["0.0019000000"]
    )
    return_period: str = Field(..., description="Return period label.", examples=["1d"])
    return_convention: str = Field(
        ..., description="Return convention label.", examples=["total_return_index"]
    )
    series_currency: str = Field(..., description="Series currency code.", examples=["USD"])
    quality_status: str = Field(..., description="Quality status.", examples=["accepted"])

    model_config = ConfigDict()


class IndexPriceSeriesResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["IndexSeriesWindow"] = product_name_field("IndexSeriesWindow")
    product_version: Literal["v1"] = product_version_field()
    index_id: str = Field(..., description="Index identifier.", examples=["IDX_MSCI_WORLD_TR"])
    resolved_window: IntegrationWindow = Field(..., description="Resolved date window.")
    frequency: str = Field(..., description="Frequency label.", examples=["daily"])
    points: list[IndexPriceSeriesPoint] = Field(
        default_factory=list, description="Index price points."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Lineage metadata for deterministic replay.",
        examples=[{"contract_version": "rfc_062_v1", "source_system": "lotus-core"}],
    )

    model_config = ConfigDict()


class IndexReturnSeriesResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["IndexSeriesWindow"] = product_name_field("IndexSeriesWindow")
    product_version: Literal["v1"] = product_version_field()
    index_id: str = Field(..., description="Index identifier.", examples=["IDX_MSCI_WORLD_TR"])
    as_of_date: date = Field(
        ...,
        description="As-of date used for deterministic contract resolution.",
        examples=["2026-01-31"],
    )
    resolved_window: IntegrationWindow = Field(..., description="Resolved date window.")
    frequency: str = Field(..., description="Frequency label.", examples=["daily"])
    request_fingerprint: str = Field(
        ...,
        description="Deterministic request fingerprint for the raw index return series scope.",
        examples=["9ccdb0a1df40f0690241a5b52e9f1c1d"],
    )
    points: list[IndexReturnSeriesPoint] = Field(
        default_factory=list, description="Index return points."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Lineage metadata for deterministic replay.",
        examples=[{"contract_version": "rfc_062_v1", "source_system": "lotus-core"}],
    )

    model_config = ConfigDict()


class BenchmarkReturnSeriesResponse(BaseModel):
    benchmark_id: str = Field(
        ..., description="Benchmark identifier.", examples=["BMK_GLOBAL_BALANCED_60_40"]
    )
    as_of_date: date = Field(
        ...,
        description="As-of date used for deterministic contract resolution.",
        examples=["2026-01-31"],
    )
    resolved_window: IntegrationWindow = Field(..., description="Resolved date window.")
    frequency: str = Field(..., description="Frequency label.", examples=["daily"])
    request_fingerprint: str = Field(
        ...,
        description="Deterministic request fingerprint for the raw benchmark return series scope.",
        examples=["f4ea7426d13c0b95bbfd8d7d9dfb29af"],
    )
    points: list[BenchmarkReturnSeriesPoint] = Field(
        default_factory=list,
        description="Raw benchmark return points from upstream provider.",
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Lineage metadata for deterministic replay.",
        examples=[{"contract_version": "rfc_062_v1", "source_system": "lotus-core"}],
    )

    model_config = ConfigDict()


class RiskFreeSeriesPoint(BaseModel):
    series_date: date = Field(..., description="Series date.", examples=["2026-01-02"])
    value: Decimal = Field(..., description="Risk-free series value.", examples=["0.0350000000"])
    value_convention: str = Field(
        ..., description="Value convention label.", examples=["annualized_rate"]
    )
    day_count_convention: str | None = Field(
        None,
        description="Day-count convention for annualized rate interpretation.",
        examples=["act_360"],
    )
    compounding_convention: str | None = Field(
        None,
        description="Compounding convention associated with rate series.",
        examples=["simple"],
    )
    series_currency: str = Field(..., description="Series currency code.", examples=["USD"])
    quality_status: str = Field(..., description="Quality status.", examples=["accepted"])

    model_config = ConfigDict()


class RiskFreeSeriesResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["RiskFreeSeriesWindow"] = product_name_field("RiskFreeSeriesWindow")
    product_version: Literal["v1"] = product_version_field()
    currency: str = Field(..., description="Series currency code.", examples=["USD"])
    as_of_date: date = Field(
        ...,
        description="As-of date used for deterministic contract resolution.",
        examples=["2026-01-31"],
    )
    series_mode: Literal["annualized_rate_series", "return_series"] = Field(
        ...,
        description="Series mode returned by the endpoint.",
        examples=["annualized_rate_series"],
    )
    resolved_window: IntegrationWindow = Field(..., description="Resolved date window.")
    frequency: str = Field(..., description="Frequency label.", examples=["daily"])
    request_fingerprint: str = Field(
        ...,
        description="Deterministic request fingerprint for the raw risk-free series scope.",
        examples=["6dfc8591d95a53060efd94ddca9a266e"],
    )
    points: list[RiskFreeSeriesPoint] = Field(
        default_factory=list, description="Risk-free series points."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Lineage metadata for returned records.",
        examples=[{"contract_version": "rfc_062_v1", "source_system": "lotus-core"}],
    )

    model_config = ConfigDict()


class CoverageRequest(BaseModel):
    window: IntegrationWindow = Field(..., description="Coverage observation window.")

    model_config = ConfigDict()


class CoverageResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["DataQualityCoverageReport"] = product_name_field(
        "DataQualityCoverageReport"
    )
    product_version: Literal["v1"] = product_version_field()
    request_fingerprint: str = Field(
        ...,
        description="Deterministic request fingerprint for the coverage diagnostics scope.",
        examples=["2cb014be96ad2cb65ce1833d9f2b88a2"],
    )
    observed_start_date: date | None = Field(
        None,
        description="Observed first date in data window.",
        examples=["2026-01-01"],
    )
    observed_end_date: date | None = Field(
        None,
        description="Observed last date in data window.",
        examples=["2026-01-31"],
    )
    expected_start_date: date = Field(
        ...,
        description="Expected start date from request window.",
        examples=["2026-01-01"],
    )
    expected_end_date: date = Field(
        ...,
        description="Expected end date from request window.",
        examples=["2026-01-31"],
    )
    total_points: int = Field(
        ...,
        description="Total points available in observed window.",
        examples=[31],
    )
    missing_dates_count: int = Field(
        ...,
        description="Count of missing calendar dates within expected window.",
        examples=[2],
    )
    missing_dates_sample: list[date] = Field(
        default_factory=list,
        description="Sample of missing dates in the expected window.",
        examples=[["2026-01-10", "2026-01-21"]],
    )
    quality_status_distribution: dict[str, int] = Field(
        default_factory=dict,
        description="Quality status distribution over observed points.",
        examples=[{"accepted": 29, "estimated": 2}],
    )

    model_config = ConfigDict()


class ClassificationTaxonomyRequest(BaseModel):
    as_of_date: date = Field(
        ..., description="As-of date for taxonomy resolution.", examples=["2026-01-31"]
    )
    taxonomy_scope: str | None = Field(
        None,
        description=(
            "Optional taxonomy scope filter such as `index`, `instrument`, or other "
            "governed source scopes. Omitting the field returns all effective scopes."
        ),
        examples=["index"],
    )

    model_config = ConfigDict()


class ClassificationTaxonomyEntry(BaseModel):
    classification_set_id: str = Field(
        ...,
        description="Classification taxonomy set identifier.",
        examples=["wm_global_taxonomy_v1"],
    )
    taxonomy_scope: str = Field(..., description="Taxonomy scope.", examples=["index"])
    dimension_name: str = Field(
        ..., description="Classification dimension name.", examples=["sector"]
    )
    dimension_value: str = Field(
        ..., description="Classification dimension value.", examples=["technology"]
    )
    dimension_description: str | None = Field(
        None,
        description="Human-readable dimension description.",
        examples=["Technology sector classification"],
    )
    effective_from: date = Field(..., description="Effective start date.", examples=["2025-01-01"])
    effective_to: date | None = Field(
        None,
        description="Effective end date.",
        examples=["2026-12-31"],
    )
    quality_status: str = Field(..., description="Quality status.", examples=["accepted"])

    model_config = ConfigDict()


class ClassificationTaxonomyResponse(SourceDataProductRuntimeMetadata):
    product_name: Literal["InstrumentReferenceBundle"] = product_name_field(
        "InstrumentReferenceBundle"
    )
    product_version: Literal["v1"] = product_version_field()
    as_of_date: date = Field(
        ...,
        description="As-of date used for taxonomy response.",
        examples=["2026-01-31"],
    )
    records: list[ClassificationTaxonomyEntry] = Field(
        default_factory=list,
        description="Classification taxonomy entries effective on the requested date.",
        examples=[[{"classification_set_id": "wm_global_taxonomy_v1", "dimension_name": "sector"}]],
    )
    taxonomy_version: str = Field(
        "rfc_062_v1",
        description="Taxonomy contract version exposed by query service.",
        examples=["rfc_062_v1"],
    )
    request_fingerprint: str = Field(
        ...,
        description="Deterministic request fingerprint for the taxonomy response scope.",
        examples=["d87368035df24ff9a42cb6e586e17ac7"],
    )

    model_config = ConfigDict()
