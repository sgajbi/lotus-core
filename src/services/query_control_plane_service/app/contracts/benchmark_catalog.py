"""Public contracts for the effective benchmark definition catalog."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from portfolio_common.source_data_product_metadata import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)
from pydantic import BaseModel, ConfigDict, Field

from .benchmark_definition import BenchmarkComponentResponse


class BenchmarkCatalogRequest(BaseModel):
    """Filters for effective benchmark master records."""

    as_of_date: date = Field(
        ...,
        description="Point-in-time date for benchmark catalog retrieval.",
        examples=["2026-01-31"],
    )
    benchmark_type: str | None = Field(
        None, description="Optional benchmark type filter.", examples=["composite"]
    )
    benchmark_currency: str | None = Field(
        None, description="Optional benchmark currency filter.", examples=["USD"]
    )
    benchmark_status: str | None = Field(
        None, description="Optional benchmark status filter.", examples=["active"]
    )

    model_config = ConfigDict()


class BenchmarkCatalogRecord(BaseModel):
    """One effective benchmark definition in the catalog."""

    benchmark_id: str = Field(
        ..., description="Canonical benchmark identifier.", examples=["BMK_GLOBAL_BALANCED_60_40"]
    )
    benchmark_name: str = Field(
        ..., description="Benchmark display name.", examples=["Global Balanced 60/40 (TR)"]
    )
    benchmark_type: Literal["single_index", "composite"] = Field(
        ..., description="Benchmark composition type.", examples=["composite"]
    )
    benchmark_currency: str = Field(..., description="Benchmark base currency.", examples=["USD"])
    return_convention: Literal["price_return_index", "total_return_index"] = Field(
        ..., description="Benchmark return convention.", examples=["total_return_index"]
    )
    benchmark_status: str = Field(
        ..., description="Benchmark lifecycle status.", examples=["active"]
    )
    benchmark_family: str | None = Field(
        None, description="Benchmark family grouping.", examples=["multi_asset_strategic"]
    )
    benchmark_provider: str | None = Field(
        None, description="Reference data provider.", examples=["MSCI"]
    )
    rebalance_frequency: str | None = Field(
        None, description="Benchmark rebalance cadence.", examples=["quarterly"]
    )
    classification_set_id: str | None = Field(
        None,
        description="Classification taxonomy set identifier.",
        examples=["wm_global_taxonomy_v1"],
    )
    classification_labels: dict[str, str] = Field(
        default_factory=dict,
        description="Canonical benchmark classification labels.",
        examples=[{"asset_class": "multi_asset", "region": "global"}],
    )
    effective_from: date = Field(
        ..., description="Definition effective start date.", examples=["2025-01-01"]
    )
    effective_to: date | None = Field(
        None, description="Definition effective end date.", examples=["2026-12-31"]
    )
    quality_status: str = Field(
        ..., description="Definition source quality status.", examples=["accepted"]
    )
    source_timestamp: datetime | None = Field(
        None, description="Source publication timestamp.", examples=["2026-01-31T08:00:00Z"]
    )
    source_vendor: str | None = Field(
        None, description="Source vendor identifier.", examples=["MSCI"]
    )
    source_record_id: str | None = Field(
        None, description="Source record identifier for replay.", examples=["bmk_60_40_v20260131"]
    )
    components: list[BenchmarkComponentResponse] = Field(
        default_factory=list, description="Effective benchmark constituents."
    )
    completeness_status: Literal["COMPLETE", "PARTIAL"] = Field(
        ..., description="Whether effective constituents sum to one.", examples=["COMPLETE"]
    )
    completeness_reason: str = Field(
        ...,
        description="Bounded constituent completeness reason.",
        examples=["BENCHMARK_DEFINITION_COMPLETE"],
    )
    total_component_weight: Decimal = Field(
        ..., description="Sum of effective constituent weights.", examples=["1.0000000000"]
    )
    contract_version: str = Field(
        "rfc_062_v1", description="Benchmark definition contract version.", examples=["rfc_062_v1"]
    )

    model_config = ConfigDict()


class BenchmarkCatalogResponse(SourceDataProductRuntimeMetadata):
    """Effective benchmark catalog with deterministic collection-level source proof."""

    product_name: Literal["BenchmarkDefinition"] = product_name_field("BenchmarkDefinition")
    product_version: Literal["v1"] = product_version_field()
    records: list[BenchmarkCatalogRecord] = Field(
        default_factory=list,
        description="Benchmark definition records effective for the requested date.",
        examples=[[{"benchmark_id": "BMK_GLOBAL_BALANCED_60_40", "benchmark_type": "composite"}]],
    )
    record_count: int = Field(
        ..., description="Number of effective benchmark records returned.", examples=[12]
    )
    completeness_status: Literal["COMPLETE", "PARTIAL", "EMPTY"] = Field(
        ...,
        description="Aggregate constituent completeness across returned records.",
        examples=["COMPLETE"],
    )

    model_config = ConfigDict()
