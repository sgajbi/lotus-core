"""Public contracts for benchmark constituent windows."""

from datetime import date
from decimal import Decimal
from typing import Literal

from portfolio_common.source_data_product_metadata import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator


class BenchmarkCompositionDateWindow(BaseModel):
    """Inclusive business-date window for benchmark composition evidence."""

    start_date: date = Field(
        ..., description="Inclusive composition window start date.", examples=["2026-01-01"]
    )
    end_date: date = Field(
        ..., description="Inclusive composition window end date.", examples=["2026-03-31"]
    )

    @model_validator(mode="after")
    def validate_order(self) -> "BenchmarkCompositionDateWindow":
        if self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        return self

    model_config = ConfigDict()


class BenchmarkCompositionWindowRequest(BaseModel):
    """Request for all effective constituent segments overlapping a date window."""

    window: BenchmarkCompositionDateWindow = Field(
        ...,
        description="Window used to resolve overlapping benchmark composition segments.",
    )

    model_config = ConfigDict()


class BenchmarkConstituentSegmentResponse(BaseModel):
    """One effective constituent-weight segment in the requested window."""

    index_id: str = Field(
        ..., description="Canonical constituent index identifier.", examples=["IDX_MSCI_WORLD_TR"]
    )
    composition_weight: Decimal = Field(
        ..., description="Constituent weight as a decimal ratio.", examples=["0.6000000000"]
    )
    composition_effective_from: date = Field(
        ..., description="Segment effective start date.", examples=["2026-01-01"]
    )
    composition_effective_to: date | None = Field(
        None,
        description="Segment effective end date, null when open-ended.",
        examples=["2026-03-31"],
    )
    rebalance_event_id: str | None = Field(
        None,
        description="Rebalance event identifier linking related composition changes.",
        examples=["rebalance_2026q1"],
    )

    model_config = ConfigDict()


class BenchmarkCompositionWindowResponse(SourceDataProductRuntimeMetadata):
    """Cross-rebalance constituent segments with completeness and source evidence."""

    product_name: Literal["BenchmarkConstituentWindow"] = product_name_field(
        "BenchmarkConstituentWindow"
    )
    product_version: Literal["v1"] = product_version_field()
    benchmark_id: str = Field(
        ..., description="Canonical benchmark identifier.", examples=["BMK_GLOBAL_BALANCED_60_40"]
    )
    benchmark_currency: str = Field(
        ..., description="Benchmark currency across the requested window.", examples=["USD"]
    )
    resolved_window: BenchmarkCompositionDateWindow = Field(
        ..., description="Resolved inclusive composition window."
    )
    segments: list[BenchmarkConstituentSegmentResponse] = Field(
        default_factory=list,
        description="Ordered benchmark composition segments overlapping the requested window.",
    )
    completeness_status: Literal["COMPLETE", "PARTIAL"] = Field(
        ...,
        description="Whether constituent weights form a unit-weight benchmark at every boundary.",
        examples=["COMPLETE"],
    )
    completeness_reason: str = Field(
        ...,
        description="Bounded reason code explaining window completeness.",
        examples=["BENCHMARK_COMPOSITION_WINDOW_COMPLETE"],
    )
    incomplete_period_starts: list[date] = Field(
        default_factory=list,
        description="Composition boundary dates where active constituent weights are incomplete.",
        examples=[["2026-02-01"]],
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Compatibility lineage metadata for deterministic replay.",
        examples=[
            {
                "contract_version": "rfc_062_v1",
                "source_system": "lotus-core",
                "generated_by": "query_control_plane_service",
            }
        ],
    )

    model_config = ConfigDict()
