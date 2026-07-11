"""Public contracts for effective benchmark definition evidence."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from portfolio_common.source_data_product_metadata import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)
from pydantic import BaseModel, ConfigDict, Field


class BenchmarkDefinitionRequest(BaseModel):
    """Point-in-time benchmark definition resolution request."""

    as_of_date: date = Field(
        ...,
        description="Point-in-time date used to resolve the benchmark definition version.",
        examples=["2026-01-31"],
    )

    model_config = ConfigDict()


class BenchmarkComponentResponse(BaseModel):
    """One effective index constituent in a benchmark definition."""

    index_id: str = Field(
        ...,
        description="Canonical constituent index identifier.",
        examples=["IDX_MSCI_WORLD_TR"],
    )
    composition_weight: Decimal = Field(
        ..., description="Constituent weight as a decimal ratio.", examples=["0.6000000000"]
    )
    composition_effective_from: date = Field(
        ..., description="Constituent effective start date.", examples=["2026-01-01"]
    )
    composition_effective_to: date | None = Field(
        None,
        description="Constituent effective end date, null when open-ended.",
        examples=["2026-03-31"],
    )
    rebalance_event_id: str | None = Field(
        None,
        description="Rebalance event identifier linking related composition changes.",
        examples=["rebalance_2026q1"],
    )

    model_config = ConfigDict()


class BenchmarkDefinitionResponse(SourceDataProductRuntimeMetadata):
    """Effective benchmark master and constituents with source-owned support evidence."""

    product_name: Literal["BenchmarkDefinition"] = product_name_field("BenchmarkDefinition")
    product_version: Literal["v1"] = product_version_field()
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
        None,
        description="Definition effective end date, null when open-ended.",
        examples=["2026-12-31"],
    )
    quality_status: str = Field(
        ..., description="Resolved definition quality status.", examples=["accepted"]
    )
    source_timestamp: datetime | None = Field(
        None,
        description="Source publication timestamp for the definition.",
        examples=["2026-01-31T08:00:00Z"],
    )
    source_vendor: str | None = Field(
        None, description="Source vendor identifier.", examples=["MSCI"]
    )
    source_record_id: str | None = Field(
        None,
        description="Source record identifier for deterministic replay.",
        examples=["bmk_60_40_v20260131"],
    )
    components: list[BenchmarkComponentResponse] = Field(
        default_factory=list,
        description="Effective benchmark constituents.",
        examples=[
            [
                {
                    "index_id": "IDX_MSCI_WORLD_TR",
                    "composition_weight": "0.6000000000",
                    "composition_effective_from": "2026-01-01",
                }
            ]
        ],
    )
    completeness_status: Literal["COMPLETE", "PARTIAL"] = Field(
        ...,
        description="Whether effective constituents form a complete unit-weight definition.",
        examples=["COMPLETE"],
    )
    completeness_reason: str = Field(
        ...,
        description="Bounded reason code explaining definition completeness.",
        examples=["BENCHMARK_DEFINITION_COMPLETE"],
    )
    total_component_weight: Decimal = Field(
        ..., description="Sum of effective constituent weights.", examples=["1.0000000000"]
    )
    contract_version: str = Field(
        "rfc_062_v1",
        description="Benchmark definition integration contract version.",
        examples=["rfc_062_v1"],
    )

    model_config = ConfigDict()
