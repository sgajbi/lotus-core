"""API contracts for governed index price and return series windows."""

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


class IndexSeriesRequest(BaseModel):
    """Request a daily canonical index series window."""

    as_of_date: date = Field(
        ..., description="As-of date used for deterministic contract resolution."
    )
    window: IntegrationWindow = Field(..., description="Date window for series extraction.")
    frequency: Literal["daily"] = Field(
        ..., description="Requested output frequency. Currently only daily is supported."
    )
    target_currency: str | None = Field(
        None, description="Optional target currency context for price series responses."
    )

    model_config = ConfigDict()


class IndexPriceSeriesPoint(BaseModel):
    """One canonical index price point."""

    series_date: date
    index_price: Decimal
    series_currency: str
    value_convention: str
    quality_status: str


class IndexReturnSeriesPoint(BaseModel):
    """One canonical index return point."""

    series_date: date
    index_return: Decimal
    return_period: str
    return_convention: str
    series_currency: str
    quality_status: str


class IndexSeriesResponseMetadata(SourceDataProductRuntimeMetadata):
    """Shared contract fields for the two IndexSeriesWindow representations."""

    product_name: Literal["IndexSeriesWindow"] = product_name_field("IndexSeriesWindow")
    product_version: Literal["v1"] = product_version_field()
    index_id: str
    resolved_window: IntegrationWindow
    frequency: str
    request_fingerprint: str = Field(
        ..., description="Deterministic fingerprint of the requested index series scope."
    )
    record_count: int = Field(..., ge=0, description="Number of canonical points returned.")
    completeness_status: Literal["COMPLETE", "PARTIAL", "EMPTY"] = Field(
        ..., description="Window boundary and row-quality completeness posture."
    )
    lineage: dict[str, str] = Field(
        default_factory=dict, description="Compatibility lineage metadata for existing consumers."
    )


class IndexPriceSeriesResponse(IndexSeriesResponseMetadata):
    """Canonical index price observations and source-owned proof."""

    request_fingerprint: str = Field(
        ...,
        description="Deterministic request fingerprint for the raw index price series scope.",
    )
    points: list[IndexPriceSeriesPoint] = Field(default_factory=list)


class IndexReturnSeriesResponse(IndexSeriesResponseMetadata):
    """Canonical index return observations and source-owned proof."""

    request_fingerprint: str = Field(
        ...,
        description="Deterministic request fingerprint for the raw index return series scope.",
    )
    points: list[IndexReturnSeriesPoint] = Field(default_factory=list)
