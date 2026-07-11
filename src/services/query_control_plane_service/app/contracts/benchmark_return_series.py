"""API contracts for governed benchmark return series windows."""

from datetime import date
from decimal import Decimal
from typing import Literal

from portfolio_common.source_data_product_metadata import (
    SourceDataProductRuntimeMetadata,
    product_name_field,
    product_version_field,
)
from pydantic import BaseModel, ConfigDict, Field

from .common import IntegrationWindow


class BenchmarkReturnSeriesRequest(BaseModel):
    """Request a daily canonical benchmark return series window."""

    as_of_date: date = Field(
        ...,
        description="As-of date used for deterministic contract resolution.",
        examples=["2026-01-31"],
    )
    window: IntegrationWindow = Field(..., description="Date window for series extraction.")
    frequency: Literal["daily"] = Field(
        ...,
        description="Requested output frequency label. Currently only daily is supported.",
        examples=["daily"],
    )

    model_config = ConfigDict()


class BenchmarkReturnSeriesPoint(BaseModel):
    """One canonical benchmark return point."""

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


class BenchmarkReturnSeriesResponse(SourceDataProductRuntimeMetadata):
    """Canonical benchmark returns with deterministic source proof."""

    product_name: Literal["BenchmarkReturnSeriesWindow"] = product_name_field(
        "BenchmarkReturnSeriesWindow"
    )
    product_version: Literal["v1"] = product_version_field()
    benchmark_id: str = Field(
        ..., description="Benchmark identifier.", examples=["BMK_GLOBAL_BALANCED_60_40"]
    )
    resolved_window: IntegrationWindow = Field(..., description="Resolved date window.")
    frequency: str = Field(..., description="Frequency label.", examples=["daily"])
    request_fingerprint: str = Field(
        ...,
        description="Deterministic request fingerprint for the raw benchmark return series scope.",
        examples=["f4ea7426d13c0b95bbfd8d7d9dfb29af"],
    )
    record_count: int = Field(..., ge=0, description="Number of canonical points returned.")
    completeness_status: Literal["COMPLETE", "PARTIAL", "EMPTY"] = Field(
        ..., description="Window boundary and row-quality completeness posture."
    )
    points: list[BenchmarkReturnSeriesPoint] = Field(
        default_factory=list,
        description="Raw benchmark return points from the authoritative source.",
    )
    lineage: dict[str, str] = Field(
        default_factory=dict,
        description="Lineage metadata for deterministic replay.",
        examples=[{"contract_version": "rfc_062_v1", "source_system": "lotus-core"}],
    )

    model_config = ConfigDict()
